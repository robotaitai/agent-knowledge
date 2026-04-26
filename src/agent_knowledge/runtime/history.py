"""Lightweight project history layer for agent-knowledge vaults.

History is intentionally thin. It records what happened over time without
becoming a second knowledge base.

    Memory/  = what is true now (curated, authoritative)
    History/ = what happened over time (lightweight diary)
    Evidence/= imported/extracted material (non-canonical sources)
    Outputs/ = generated helper artifacts

Structure created under the vault:
    History/
        history.md       -- human-readable entrypoint, recent milestones
        timeline/        -- sparse milestone notes (only for significant events)
        events.ndjson    -- append-only machine-readable event log

Design rules:
- No database, no full transcript dumps, no verbatim git logs
- One event per type per natural dedup unit (see below)
- Timeline notes only for significant milestones (init, backfill, release)
- history.md is always < 150 lines
"""

from __future__ import annotations

import datetime
import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any

_HISTORY_DIR = "History"
_EVENTS_FILE = "History/events.ndjson"
_HISTORY_MD = "History/history.md"
_TIMELINE_DIR = "History/timeline"


# --------------------------------------------------------------------------- #
# Utilities                                                                    #
# --------------------------------------------------------------------------- #


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


def _this_month() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m")


def _safe_slug(text: str, maxlen: int = 40) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:maxlen]


# --------------------------------------------------------------------------- #
# Event log read/write                                                         #
# --------------------------------------------------------------------------- #


def read_events(vault_dir: Path, *, limit: int | None = None) -> list[dict[str, Any]]:
    """Read events from events.ndjson. Returns newest-first."""
    events_path = vault_dir / _EVENTS_FILE
    if not events_path.is_file():
        return []
    events: list[dict[str, Any]] = []
    for line in events_path.read_text(errors="replace").splitlines():
        s = line.strip()
        if not s:
            continue
        try:
            events.append(json.loads(s))
        except (json.JSONDecodeError, ValueError):
            continue
    events.reverse()
    return events[:limit] if limit else events


def _event_exists_for_day(vault_dir: Path, event_type: str, date: str) -> bool:
    """True if an event of this type was logged on the given YYYY-MM-DD date."""
    events_path = vault_dir / _EVENTS_FILE
    if not events_path.is_file():
        return False
    prefix = date[:10]
    for line in events_path.read_text(errors="replace").splitlines():
        s = line.strip()
        if not s:
            continue
        try:
            ev = json.loads(s)
            if ev.get("type") == event_type and ev.get("ts", "")[:10] == prefix:
                return True
        except (json.JSONDecodeError, ValueError):
            continue
    return False


def _event_exists_for_month(vault_dir: Path, event_type: str) -> bool:
    """True if an event of this type was logged in the current month."""
    events_path = vault_dir / _EVENTS_FILE
    if not events_path.is_file():
        return False
    month = _this_month()
    for line in events_path.read_text(errors="replace").splitlines():
        s = line.strip()
        if not s:
            continue
        try:
            ev = json.loads(s)
            if ev.get("type") == event_type and ev.get("ts", "")[:7] == month:
                return True
        except (json.JSONDecodeError, ValueError):
            continue
    return False


def _event_exists_ever(vault_dir: Path, event_type: str) -> bool:
    """True if any event of this type has ever been logged."""
    events_path = vault_dir / _EVENTS_FILE
    if not events_path.is_file():
        return False
    for line in events_path.read_text(errors="replace").splitlines():
        s = line.strip()
        if not s:
            continue
        try:
            ev = json.loads(s)
            if ev.get("type") == event_type:
                return True
        except (json.JSONDecodeError, ValueError):
            continue
    return False


def _release_exists(vault_dir: Path, tag_name: str) -> bool:
    """True if a release event for this tag already exists."""
    events_path = vault_dir / _EVENTS_FILE
    if not events_path.is_file():
        return False
    for line in events_path.read_text(errors="replace").splitlines():
        s = line.strip()
        if not s:
            continue
        try:
            ev = json.loads(s)
            if ev.get("type") == "release" and tag_name in ev.get("tags", []):
                return True
        except (json.JSONDecodeError, ValueError):
            continue
    return False


def append_event(
    vault_dir: Path,
    event_type: str,
    *,
    summary: str,
    source_tool: str = "cli",
    project_slug: str = "",
    touched_branches: list[str] | None = None,
    touched_paths: list[str] | None = None,
    related_commits: list[str] | None = None,
    related_decisions: list[str] | None = None,
    related_notes: list[str] | None = None,
    tags: list[str] | None = None,
    confidence: str | None = None,
    dry_run: bool = False,
) -> bool:
    """Append an event to events.ndjson.

    Caller is responsible for deduplication checks before calling this.
    Returns True if written, False if dry_run.
    """
    event: dict[str, Any] = {
        "ts": _now_iso(),
        "type": event_type,
        "tool": source_tool,
        "slug": project_slug,
        "summary": summary,
    }
    if touched_branches:
        event["branches"] = touched_branches[:10]
    if touched_paths:
        event["paths"] = touched_paths[:10]
    if related_commits:
        event["commits"] = related_commits[:5]
    if related_decisions:
        event["decisions"] = related_decisions[:5]
    if related_notes:
        event["notes"] = related_notes[:5]
    if tags:
        event["tags"] = tags[:10]
    if confidence:
        event["confidence"] = confidence

    if dry_run:
        return False

    events_path = vault_dir / _EVENTS_FILE
    events_path.parent.mkdir(parents=True, exist_ok=True)
    with events_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
    return True


def log_event(
    vault_dir: Path,
    event_type: str,
    *,
    summary: str,
    source_tool: str = "cli",
    project_slug: str = "",
    touched_branches: list[str] | None = None,
    related_commits: list[str] | None = None,
    tags: list[str] | None = None,
    dry_run: bool = False,
    dedup: str = "day",
) -> bool:
    """Append an event with built-in deduplication.

    dedup options:
      "day"   — one event of this type per day (default)
      "month" — one event of this type per month
      "ever"  — only log once ever
      "none"  — always append (no dedup)
    """
    if not dry_run:
        if dedup == "day" and _event_exists_for_day(vault_dir, event_type, _today()):
            return False
        if dedup == "month" and _event_exists_for_month(vault_dir, event_type):
            return False
        if dedup == "ever" and _event_exists_ever(vault_dir, event_type):
            return False

    return append_event(
        vault_dir,
        event_type,
        summary=summary,
        source_tool=source_tool,
        project_slug=project_slug,
        touched_branches=touched_branches,
        related_commits=related_commits,
        tags=tags,
        dry_run=dry_run,
    )


# --------------------------------------------------------------------------- #
# History structure initialization                                             #
# --------------------------------------------------------------------------- #


def init_history(vault_dir: Path, project_slug: str) -> None:
    """Ensure the History/ structure exists with empty scaffolding."""
    (vault_dir / _HISTORY_DIR).mkdir(parents=True, exist_ok=True)
    (vault_dir / _TIMELINE_DIR).mkdir(parents=True, exist_ok=True)

    events_path = vault_dir / _EVENTS_FILE
    if not events_path.is_file():
        events_path.touch()

    history_md = vault_dir / _HISTORY_MD
    if not history_md.is_file():
        _rebuild_history_md(vault_dir, project_slug, [])


def history_exists(vault_dir: Path) -> bool:
    """True if the History/ layer has been initialized."""
    return (vault_dir / _HISTORY_DIR).is_dir()


# --------------------------------------------------------------------------- #
# History.md generation                                                        #
# --------------------------------------------------------------------------- #


def _rebuild_history_md(
    vault_dir: Path,
    project_slug: str,
    events: list[dict[str, Any]],
) -> None:
    """Regenerate History/history.md from events (always < 150 lines)."""
    today = _today()
    recent = events[:15]

    lines: list[str] = [
        f"---\narea: history\nproject: {project_slug}\nupdated: {today}\n---\n",
        "\n# Project History\n\n",
        "Lightweight project diary. What happened, when, in which area.\n\n",
        "For current truth, see [Memory/MEMORY.md](../Memory/MEMORY.md).\n",
        "This is not a git replacement.\n",
    ]

    # Timeline notes (sparse — only when they exist)
    timeline_dir = vault_dir / _TIMELINE_DIR
    if timeline_dir.is_dir():
        tl_notes = sorted(
            [f for f in timeline_dir.glob("*.md") if f.is_file()],
            reverse=True,
        )[:5]
        if tl_notes:
            lines.append("\n## Timeline Notes\n\n")
            for tn in tl_notes:
                lines.append(f"- [{tn.stem}](timeline/{tn.name})\n")

    # Recent activity
    if recent:
        lines.append("\n## Recent Activity\n\n")
        for ev in recent:
            ts = ev.get("ts", "")[:10]
            summary = ev.get("summary", "")
            etype = ev.get("type", "event")
            branches = ev.get("branches", [])
            btag = f" ({', '.join(branches[:3])})" if branches else ""
            tag_list = ev.get("tags", [])
            ttag = f" [{', '.join(tag_list[:2])}]" if tag_list else ""
            lines.append(f"- **{ts}** `{etype}`{ttag} — {summary}{btag}\n")

    lines.append("\n## Reference\n\n")
    lines.append("- [Memory root](../Memory/MEMORY.md)\n")
    lines.append("- [STATUS](../STATUS.md)\n")
    lines.append("- [events.ndjson](events.ndjson) — machine-readable log\n")
    lines.append("\n---\n\n")
    lines.append("History is lightweight by design. Current truth lives in Memory/.\n")

    path = vault_dir / _HISTORY_MD
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(lines), encoding="utf-8")


# --------------------------------------------------------------------------- #
# Timeline notes                                                               #
# --------------------------------------------------------------------------- #


def _create_timeline_note(
    vault_dir: Path,
    title: str,
    content: str,
    date: str | None = None,
    slug: str | None = None,
) -> Path:
    """Create a timeline note. Returns the path (existing or new)."""
    d = date or _today()
    s = slug or _safe_slug(title)
    name = f"{d}-{s}.md"
    tl_dir = vault_dir / _TIMELINE_DIR
    tl_dir.mkdir(parents=True, exist_ok=True)
    note_path = tl_dir / name
    if not note_path.exists():
        note_path.write_text(content, encoding="utf-8")
    return note_path


# --------------------------------------------------------------------------- #
# Git helpers                                                                  #
# --------------------------------------------------------------------------- #


def _git(repo_root: Path, *args: str, timeout: int = 10) -> str:
    """Run a git command. Returns stdout or '' on failure."""
    try:
        r = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return r.stdout if r.returncode == 0 else ""
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""


def _git_tags(repo_root: Path, max_tags: int = 10) -> list[dict[str, str]]:
    out = _git(repo_root, "tag", "--sort=-creatordate",
               "--format=%(refname:short)|%(creatordate:short)")
    tags = []
    for line in out.strip().splitlines()[:max_tags]:
        parts = line.split("|", 1)
        if len(parts) == 2 and parts[0].strip():
            tags.append({"name": parts[0].strip(), "date": parts[1].strip()[:10]})
    return tags


def _git_recent_commits(repo_root: Path, max_commits: int = 20) -> list[dict[str, str]]:
    out = _git(repo_root, "log", f"--max-count={max_commits}",
               "--format=%H|%ai|%s", "--no-merges")
    commits = []
    for line in out.strip().splitlines():
        parts = line.split("|", 2)
        if len(parts) == 3:
            commits.append({
                "hash": parts[0][:8],
                "date": parts[1][:10],
                "message": parts[2][:100].strip(),
            })
    return commits


def _git_first_commit_date(repo_root: Path) -> str:
    out = _git(repo_root, "log", "--reverse", "--format=%ai")
    lines = out.strip().splitlines()
    return lines[0][:10] if lines else ""


def _git_commit_count(repo_root: Path) -> int:
    out = _git(repo_root, "rev-list", "--count", "HEAD")
    try:
        return int(out.strip())
    except ValueError:
        return 0


def _git_branch_names(repo_root: Path) -> list[str]:
    out = _git(repo_root, "branch", "-r")
    names = []
    for line in out.strip().splitlines():
        b = line.strip().lstrip("* ").replace("origin/", "")
        if b and b != "HEAD":
            names.append(b)
    return names[:10]


# --------------------------------------------------------------------------- #
# Backfill                                                                     #
# --------------------------------------------------------------------------- #


def _make_backfill_timeline(
    project_slug: str,
    commit_count: int,
    first_commit: str,
    tags: list[dict[str, str]],
    recent_commits: list[dict[str, str]],
    integrations: list[str],
) -> str:
    """Build the content of the initial backfill timeline note."""
    today = _today()
    tag_section = ""
    if tags:
        items = "\n".join(f"- `{t['name']}` ({t['date']})" for t in tags)
        tag_section = f"\n## Releases / Tags\n\n{items}\n"

    recent_section = ""
    if recent_commits:
        items = "\n".join(
            f"- `{c['hash']}` {c['date']} — {c['message'][:80]}"
            for c in recent_commits[:10]
        )
        recent_section = f"\n## Recent Commits (sample)\n\n{items}\n"

    integ_section = ""
    if integrations:
        integ_section = f"\n## Detected Integrations\n\n" + "\n".join(
            f"- {t}" for t in integrations
        ) + "\n"

    return f"""---
area: history
project: {project_slug}
date: {today}
type: backfill
---

# History Backfill — {project_slug}

Lightweight backfill of project history performed on {today}.
This note summarizes available signals; it is not a complete record.

## Project Overview

- **First commit:** {first_commit or 'unknown'}
- **Total commits:** {commit_count}
- **Releases:** {len(tags)}
{tag_section}{recent_section}{integ_section}
## Links

- [Memory root](../Memory/MEMORY.md)
- [events.ndjson](../events.ndjson)

---

This note was generated by `agent-knowledge backfill-history`.
It is a non-canonical summary — not a source of truth.
"""


def _update_status_backfill(repo_root: Path, vault_dir: Path) -> None:
    """Write today's date to last_backfill_import in STATUS.md."""
    status_path = vault_dir / "STATUS.md"
    if not status_path.is_file():
        return
    today = datetime.date.today().isoformat()
    content = status_path.read_text()
    import re as _re
    updated = _re.sub(
        r"^(last_backfill_import:\s*).*$",
        lambda m: f"{m.group(1)}{today}",
        content,
        flags=_re.MULTILINE,
    )
    if updated != content:
        status_path.write_text(updated)


def run_backfill(
    repo_root: Path,
    vault_dir: Path,
    *,
    project_slug: str = "",
    dry_run: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """Backfill lightweight history from git and project artifacts.

    Creates:
    - compact events in History/events.ndjson
    - a backfill timeline note in History/timeline/
    - regenerates History/history.md

    Never touches Memory/, Evidence/, or Outputs/ content.
    Idempotent: safe to run repeatedly.

    Returns a summary dict.
    """
    if not dry_run:
        init_history(vault_dir, project_slug)

    events_written = 0
    events_skipped = 0
    changes: list[str] = []

    # --- Git signals ---
    commit_count = _git_commit_count(repo_root)
    first_commit = _git_first_commit_date(repo_root)
    tags = _git_tags(repo_root, max_tags=10)
    recent_commits = _git_recent_commits(repo_root, max_commits=20)

    # project_start — only once ever
    if first_commit:
        if force or not _event_exists_ever(vault_dir, "project_start"):
            written = append_event(
                vault_dir, "project_start",
                summary=f"Project started (first commit: {first_commit}, {commit_count} total commits)",
                source_tool="git",
                project_slug=project_slug,
                dry_run=dry_run,
            )
            if written:
                events_written += 1
                changes.append(f"project_start ({first_commit})")
        else:
            events_skipped += 1

    # release — one per tag, ever
    for tag in tags:
        if force or not _release_exists(vault_dir, tag["name"]):
            written = append_event(
                vault_dir, "release",
                summary=f"Release {tag['name']}",
                source_tool="git",
                project_slug=project_slug,
                tags=[tag["name"]],
                dry_run=dry_run,
            )
            if written:
                events_written += 1
                changes.append(f"release {tag['name']}")
        else:
            events_skipped += 1

    # integration_detected — once per month per tool
    detected_tools: list[str] = []
    for tool, markers in [
        ("cursor", [".cursor"]),
        ("claude", [".claude", "CLAUDE.md"]),
        ("codex", [".codex"]),
    ]:
        if any((repo_root / m).exists() for m in markers):
            detected_tools.append(tool)
            ev_key = f"integration_{tool}"
            if force or not _event_exists_for_month(vault_dir, ev_key):
                written = append_event(
                    vault_dir, ev_key,
                    summary=f"{tool} integration detected",
                    source_tool="cli",
                    project_slug=project_slug,
                    dry_run=dry_run,
                )
                if written:
                    events_written += 1
                    changes.append(f"integration_detected: {tool}")
            else:
                events_skipped += 1

    # backfill event — once per month
    if force or not _event_exists_for_month(vault_dir, "backfill"):
        tag_names = [t["name"] for t in tags]
        summary = (
            f"History backfill: {commit_count} commits, "
            f"{len(tags)} releases, "
            f"{len(detected_tools)} integrations"
        )
        written = append_event(
            vault_dir, "backfill",
            summary=summary,
            source_tool="cli",
            project_slug=project_slug,
            tags=tag_names[:5],
            dry_run=dry_run,
        )
        if written:
            events_written += 1
            changes.append("backfill event")
    else:
        events_skipped += 1

    # --- Timeline note (only when something new was written) ---
    if not dry_run and (events_written > 0 or force):
        content = _make_backfill_timeline(
            project_slug, commit_count, first_commit,
            tags, recent_commits, detected_tools,
        )
        note = _create_timeline_note(
            vault_dir, "History backfill", content, slug="backfill",
        )
        changes.append(f"timeline: {note.name}")

    # --- Regenerate history.md ---
    if not dry_run:
        events = read_events(vault_dir, limit=20)
        _rebuild_history_md(vault_dir, project_slug, events)
        changes.append("history.md")

    # --- Update last_backfill_import in STATUS.md ---
    if not dry_run:
        _update_status_backfill(repo_root, vault_dir)

    action: str
    if dry_run:
        action = "dry-run"
    elif events_written > 0:
        action = "backfilled"
    else:
        action = "up-to-date"

    return {
        "action": action,
        "project_slug": project_slug,
        "events_written": events_written,
        "events_skipped": events_skipped,
        "changes": changes,
        "dry_run": dry_run,
        "git_commits": commit_count,
        "git_first_commit": first_commit,
        "git_tags": len(tags),
        "integrations": detected_tools,
    }
