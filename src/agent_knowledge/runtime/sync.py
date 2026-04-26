"""Sync logic: memory branch sync, git-log evidence extraction.

Also integrates:
- Capture: each sync event is recorded in Evidence/captures/ as a lightweight
  evidence item (not curated memory, never auto-promoted).
- Index: Outputs/knowledge-index.json and .md are regenerated on each sync
  so agents and humans always have a current compact catalog.
- History: incremental backfill keeps History/events.ndjson and history.md current.
"""

from __future__ import annotations

import datetime
import re
import shutil
import subprocess
from pathlib import Path


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today() -> str:
    return datetime.date.today().isoformat()


# ---------------------------------------------------------------------------
# 1. Memory branch sync: agent_docs/memory/ -> agent-knowledge/Memory/
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
    dst_dir = repo / "agent-knowledge" / "Memory"
    actions: list[str] = []

    if not src_dir.is_dir():
        actions.append("skip: agent_docs/memory/ not found")
        return actions

    if not dst_dir.is_dir():
        actions.append("skip: agent-knowledge/Memory/ not found")
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
    evidence_dir = repo / "agent-knowledge" / "Evidence" / "raw"
    actions: list[str] = []

    try:
        result = subprocess.run(
            ["git", "log", f"--oneline", f"-{count}", "--no-decorate"],
            capture_output=True,
            text=True,
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
        dst.write_text(content)
        actions.append(f"  wrote: Evidence/raw/git-recent.md ({len(lines.splitlines())} commits)")

    return actions


# ---------------------------------------------------------------------------
# 4. Update STATUS.md timestamps
# ---------------------------------------------------------------------------

def stamp_status(repo: Path, field: str) -> None:
    """Update a timestamp field in STATUS.md frontmatter."""
    status_path = repo / "agent-knowledge" / "STATUS.md"
    if not status_path.is_file():
        return

    text = status_path.read_text()
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

    status_path.write_text(text)


# ---------------------------------------------------------------------------
# 5. Capture event recording -> Evidence/captures/
# ---------------------------------------------------------------------------

def _record_sync_capture(
    repo: Path,
    *,
    memory_actions: list[str],
    dry_run: bool = False,
) -> list[str]:
    """Record a sync event in Evidence/captures/."""
    from .capture import record as capture_record

    vault = repo / "agent-knowledge"
    captures_dir = vault / "Evidence" / "captures"

    # Derive touched branches from memory-sync actions (e.g. "updated: Memory/stack.md")
    touched: list[str] = []
    for action in memory_actions:
        m = re.search(r"Memory/([^\s]+\.md)", action)
        if m:
            touched.append(m.group(1))

    # Infer project slug from the vault name
    try:
        slug = repo.name
    except Exception:
        slug = "unknown"

    _path, action = capture_record(
        captures_dir,
        event_type="sync",
        source_tool="cli",
        project_slug=slug,
        summary="Project sync: memory branches updated, git evidence extracted, history updated.",
        touched_branches=touched,
        dry_run=dry_run,
    )

    if action == "created":
        return [f"  recorded capture: Evidence/captures/"]
    elif action == "exists":
        return ["  capture: already recorded this minute (skipped)"]
    else:
        return [f"  [dry-run] would record capture: Evidence/captures/"]


# ---------------------------------------------------------------------------
# 6. Knowledge index generation -> Outputs/
# ---------------------------------------------------------------------------

def _regenerate_index(repo: Path, *, dry_run: bool = False) -> list[str]:
    """Regenerate Outputs/knowledge-index.json and .md."""
    from .index import write_index

    vault = repo / "agent-knowledge"
    if not vault.is_dir():
        return ["  skip: agent-knowledge vault not found"]

    return write_index(vault, dry_run=dry_run)


# ---------------------------------------------------------------------------
# 7. History incremental update
# ---------------------------------------------------------------------------

def _update_history(repo: Path, *, dry_run: bool = False) -> list[str]:
    """Run an incremental history backfill. Cheap when nothing is new (dedup by tag)."""
    vault = repo / "agent-knowledge"
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
# 8. Top-level sync orchestrator
# ---------------------------------------------------------------------------

def run_sync(
    repo: Path,
    *,
    dry_run: bool = False,
    source_tool: str = "cli",
) -> dict[str, list[str]]:
    """Run all sync steps. Returns a dict of step -> action list."""
    results: dict[str, list[str]] = {}

    results["memory-branches"] = sync_memory_branches(repo, dry_run=dry_run)
    results["git-evidence"] = extract_git_log(repo, dry_run=dry_run)
    results["history"] = _update_history(repo, dry_run=dry_run)
    results["capture"] = _record_sync_capture(
        repo, memory_actions=results["memory-branches"], dry_run=dry_run
    )
    results["index"] = _regenerate_index(repo, dry_run=dry_run)

    if not dry_run:
        stamp_status(repo, "last_project_sync")

    return results
