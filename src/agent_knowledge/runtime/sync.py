"""Sync logic: memory branch sync, git-log evidence extraction.

Also integrates:
- Index: Views/graph/knowledge-index.json and .md are regenerated on each sync
  so agents and humans always have a current compact catalog.
- History: incremental backfill keeps History/events.ndjson and history.md current.
"""

from __future__ import annotations

import datetime
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today() -> str:
    return datetime.date.today().isoformat()


# ---------------------------------------------------------------------------
# 1. Memory branch sync: agent_docs/memory/ -> bedrock/Memory/
# ---------------------------------------------------------------------------

def sync_memory_branches(
    repo: Path,
    *,
    dry_run: bool = False,
) -> list[str]:
    """Bidirectional sync between agent_docs/memory/ and vault Memory/.

    Always copies whichever side is newer, in both directions:
    - vault Memory/ newer than agent_docs/memory/ -> copy vault -> agent_docs
    - agent_docs/memory/ newer than vault -> copy agent_docs -> vault
    - vault has files not in agent_docs -> copy vault -> agent_docs (preserves
      changes written directly to the vault by Claude, Codex, or any other agent)

    Returns a list of action strings for reporting.
    """
    src_dir = repo / "agent_docs" / "memory"
    dst_dir = repo / "bedrock" / "Memory"
    actions: list[str] = []

    if not src_dir.is_dir():
        actions.append("skip: agent_docs/memory/ not found")
        return actions

    if not dst_dir.is_dir():
        actions.append("skip: bedrock/Memory/ not found")
        return actions

    import shutil

    # Pass 1: vault -> agent_docs for files where vault is newer or agent_docs missing
    for vault_file in sorted(dst_dir.rglob("*.md")):
        rel = vault_file.relative_to(dst_dir)
        local_file = src_dir / rel
        if not local_file.exists() or vault_file.stat().st_mtime > local_file.stat().st_mtime:
            if not dry_run:
                local_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(vault_file, local_file)
            actions.append(f"pulled: {rel} (vault -> agent_docs)")

    # Pass 2: agent_docs -> vault for files where agent_docs is newer
    for src_file in sorted(src_dir.rglob("*.md")):
        rel = src_file.relative_to(src_dir)
        dst_file = dst_dir / rel

        if dst_file.exists():
            src_mtime = src_file.stat().st_mtime
            dst_mtime = dst_file.stat().st_mtime
            if src_mtime <= dst_mtime:
                continue

        already_exists = dst_file.exists()
        if dry_run:
            verb = "would update" if already_exists else "would create"
            actions.append(f"  [dry-run] {verb}: Memory/{rel}")
        else:
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)
            verb = "updated" if already_exists else "created"
            actions.append(f"  {verb}: Memory/{rel}")

    if not actions:
        actions.append("  up to date")

    return actions



# ---------------------------------------------------------------------------
# 2. Git log extraction -> Evidence/raw/git-recent.md
# ---------------------------------------------------------------------------

def extract_git_log(
    repo: Path,
    *,
    dry_run: bool = False,
    count: int = 30,
) -> list[str]:
    """Run git log and write recent commits to Evidence/raw/git-recent.md."""
    evidence_dir = repo / "bedrock" / "Evidence" / "raw"
    actions: list[str] = []

    try:
        result = subprocess.run(
            ["git", "log", f"--oneline", f"-{count}", "--no-decorate"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(repo),
            timeout=10,
        )
        if result.returncode != 0:
            actions.append(f"  skip: git log failed ({result.stderr.strip()[:80]})")
            return actions
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        actions.append(f"  skip: git not available ({exc})")
        return actions

    lines = result.stdout.strip()
    if not lines:
        actions.append("  skip: no git history")
        return actions

    content = f"""\
---
note_type: evidence
source: git-log
extracted: {_now_iso()}
commits: {len(lines.splitlines())}
---

# Recent Git History

Last {count} commits as of {_today()}.

```
{lines}
```
"""

    dst = evidence_dir / "git-recent.md"
    if dry_run:
        actions.append(f"  [dry-run] would write: Evidence/raw/git-recent.md ({len(lines.splitlines())} commits)")
    else:
        evidence_dir.mkdir(parents=True, exist_ok=True)
        dst.write_text(content, encoding="utf-8")
        actions.append(f"  wrote: Evidence/raw/git-recent.md ({len(lines.splitlines())} commits)")

    return actions


# ---------------------------------------------------------------------------
# 4. Update STATUS.md timestamps
# ---------------------------------------------------------------------------

def stamp_status(repo: Path, field: str) -> None:
    """Update a timestamp field in STATUS.md frontmatter."""
    status_path = repo / "bedrock" / "STATUS.md"
    if not status_path.is_file():
        return

    text = status_path.read_text(encoding="utf-8")
    now = _now_iso()
    today = _today()

    pattern = re.compile(rf"^({re.escape(field)}:[ \t]*).*$", re.MULTILINE)
    if pattern.search(text):
        text = pattern.sub(rf"\g<1>{now}", text)

    display_field = field.replace("_", " ").replace("last ", "Last ")
    display_pattern = re.compile(
        rf"^(- {re.escape(display_field)}:[ \t]*`).*(`[ \t]*)$",
        re.MULTILINE | re.IGNORECASE,
    )
    if display_pattern.search(text):
        text = display_pattern.sub(rf"\g<1>{now}\2", text)

    status_path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# 5. Knowledge index generation -> Views/graph/
# ---------------------------------------------------------------------------

def _regenerate_index(repo: Path, *, dry_run: bool = False) -> list[str]:
    """Regenerate the compact knowledge index."""
    from .index import write_index

    vault = repo / "bedrock"
    if not vault.is_dir():
        return ["  skip: bedrock vault not found"]

    return write_index(vault, dry_run=dry_run)


# ---------------------------------------------------------------------------
# 6. History incremental update
# ---------------------------------------------------------------------------

def _update_history(repo: Path, *, dry_run: bool = False) -> list[str]:
    """Run an incremental history backfill. Cheap when nothing is new (dedup by tag)."""
    vault = repo / "bedrock"
    if not vault.is_dir():
        return ["  skip: vault not found"]

    try:
        from .history import run_backfill

        slug = repo.name
        result = run_backfill(repo, vault, project_slug=slug, dry_run=dry_run)
        action = result.get("action", "unknown")
        if action == "backfilled":
            n = result.get("events_written", 0)
            return [f"  history: {n} new events written"]
        elif action == "dry-run":
            return ["  [dry-run] would update history"]
        else:
            return ["  history: up-to-date"]
    except Exception as exc:
        return [f"  history: skipped ({exc})"]


# ---------------------------------------------------------------------------
# 7. Top-level sync orchestrator
# ---------------------------------------------------------------------------

def _check_framework_version(repo: Path) -> str | None:
    """Return a warning string if the recorded framework version is older than installed."""
    try:
        from agent_knowledge import __version__
        recorded: str | None = None
        for candidate in [
            repo / "bedrock" / "STATUS.md",
            repo / ".agent-project.yaml",
        ]:
            if candidate.is_file():
                text = candidate.read_text(encoding="utf-8", errors="replace")
                m = re.search(r"^framework_version:\s*(\S+)", text, re.MULTILINE)
                if m:
                    recorded = m.group(1).strip()
                    break
        if recorded is None or recorded == __version__:
            return None
        return (
            f"[bedrock] Framework version mismatch: project is on {recorded}, "
            f"installed is {__version__}. Run: bedrock refresh-system"
        )
    except Exception:
        pass
    return None


def run_sync(
    repo: Path,
    *,
    dry_run: bool = False,
    source_tool: str = "cli",
) -> dict[str, Any]:
    """Run all sync steps.

    Returns the run's ``action``, the layout versions it compared, a ``steps``
    map of step -> action list, and any ``warnings``.
    """
    from agent_knowledge.runtime import migrations as _migrations

    steps: dict[str, list[str]] = {}
    warnings: list[str] = []

    project_layout = _migrations.read_layout_version(repo)
    if project_layout > _migrations.LAYOUT_VERSION:
        # Write nothing. SessionStart runs "sync && refresh-system", so sync is
        # the first thing an older install would use to revert a newer vault --
        # guarding only refresh-system would leave the loop wide open.
        warnings.append(
            f"This project uses bedrock layout {project_layout}; this install understands "
            f"{_migrations.LAYOUT_VERSION}. Run: pip install -U project-bedrock"
        )
        return {
            "action": "blocked",
            "layout_version": _migrations.LAYOUT_VERSION,
            "project_layout_version": project_layout,
            "steps": {},
            "warnings": warnings,
        }

    version_warning = _check_framework_version(repo)
    if version_warning:
        import sys
        print(version_warning, file=sys.stderr)

    steps["memory-branches"] = sync_memory_branches(repo, dry_run=dry_run)
    steps["git-evidence"] = extract_git_log(repo, dry_run=dry_run)
    steps["history"] = _update_history(repo, dry_run=dry_run)
    steps["index"] = _regenerate_index(repo, dry_run=dry_run)

    if not dry_run:
        stamp_status(repo, "last_project_sync")

    return {
        "action": "dry-run" if dry_run else "synced",
        "layout_version": _migrations.LAYOUT_VERSION,
        "project_layout_version": project_layout,
        "steps": steps,
        "warnings": warnings,
    }
