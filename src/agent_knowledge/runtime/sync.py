"""Sync logic: memory branch sync, session rollup, git-log evidence extraction."""

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
    """Copy agent_docs/memory/*.md into the vault's Memory/ branch.

    Only copies files that are newer or missing in the vault.
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

    for src_file in sorted(src_dir.rglob("*.md")):
        rel = src_file.relative_to(src_dir)
        dst_file = dst_dir / rel

        if dst_file.exists():
            src_mtime = src_file.stat().st_mtime
            dst_mtime = dst_file.stat().st_mtime
            if src_mtime <= dst_mtime:
                continue

        if dry_run:
            verb = "would update" if dst_file.exists() else "would create"
            actions.append(f"  [dry-run] {verb}: Memory/{rel}")
        else:
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)
            verb = "updated" if dst_file.exists() else "created"
            actions.append(f"  {verb}: Memory/{rel}")

    if not actions:
        actions.append("  up to date")

    return actions


# ---------------------------------------------------------------------------
# 2. Session rollup: Sessions/*.md -> Dashboards/session-rollup.md
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)


def rollup_sessions(
    repo: Path,
    *,
    dry_run: bool = False,
    max_sessions: int = 10,
) -> list[str]:
    """Scan Sessions/ for .md files, append summaries to session-rollup.md."""
    sessions_dir = repo / "agent-knowledge" / "Sessions"
    rollup_path = repo / "agent-knowledge" / "Dashboards" / "session-rollup.md"
    actions: list[str] = []

    if not sessions_dir.is_dir():
        actions.append("skip: Sessions/ not found")
        return actions

    session_files = sorted(
        [f for f in sessions_dir.glob("*.md") if f.name != "README.md"],
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )[:max_sessions]

    if not session_files:
        actions.append("  no session files to roll up")
        return actions

    entries: list[str] = []
    for sf in session_files:
        body = sf.read_text(errors="replace")
        body = _FRONTMATTER_RE.sub("", body).strip()
        title_match = re.match(r"^#\s+(.+)", body)
        title = title_match.group(1) if title_match else sf.stem
        first_lines = "\n".join(body.split("\n")[:5])
        entries.append(f"### {title}\n\n_Source: {sf.name}_\n\n{first_lines}\n")

    rollup_body = f"""\
---
note_type: dashboard
dashboard: session-rollup
project: {repo.name}
last_updated: {_today()}
tags:
  - {repo.name}
  - dashboard
---

# Session Rollup

## Recent Sessions ({len(entries)} files)

{"---".join(entries)}

## Next Review

- Review recent sessions before the next compaction or handoff.
"""

    if dry_run:
        actions.append(f"  [dry-run] would update: Dashboards/session-rollup.md ({len(entries)} sessions)")
    else:
        rollup_path.parent.mkdir(parents=True, exist_ok=True)
        rollup_path.write_text(rollup_body)
        actions.append(f"  updated: Dashboards/session-rollup.md ({len(entries)} sessions)")

    return actions


# ---------------------------------------------------------------------------
# 3. Git log extraction -> Evidence/raw/git-recent.md
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
# 5. Top-level sync orchestrator
# ---------------------------------------------------------------------------

def run_sync(
    repo: Path,
    *,
    dry_run: bool = False,
) -> dict[str, list[str]]:
    """Run all sync steps. Returns a dict of step -> action list."""
    results: dict[str, list[str]] = {}

    results["memory-branches"] = sync_memory_branches(repo, dry_run=dry_run)
    results["session-rollup"] = rollup_sessions(repo, dry_run=dry_run)
    results["git-evidence"] = extract_git_log(repo, dry_run=dry_run)

    if not dry_run:
        stamp_status(repo, "last_project_sync")

    return results
