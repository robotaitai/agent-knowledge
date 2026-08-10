"""Ordered, idempotent migrations for the on-disk vault layout.

The package version and the layout version are deliberately separate. Most
releases change no on-disk format and leave LAYOUT_VERSION alone; bumping it is
an explicit act that says "an existing project needs work done to it".
"""

from __future__ import annotations

import re
from pathlib import Path

# Bump only when the on-disk layout changes, and add a Migration for it.
LAYOUT_VERSION = 1


def _status_path(repo_root: Path) -> Path:
    return repo_root / "bedrock" / "STATUS.md"


def read_layout_version(repo_root: Path) -> int:
    """The project's recorded layout version, or 0 when absent or unreadable.

    Degrading to 0 rather than raising matters: this runs from the SessionStart
    hook, where an exception would surface as a broken agent session.
    """
    try:
        text = _status_path(repo_root).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0
    m = re.search(r"^layout_version:\s*(.+)$", text, re.MULTILINE)
    if not m:
        return 0
    try:
        return int(m.group(1).strip().strip("\"'"))
    except ValueError:
        return 0


def stamp_layout_version(repo_root: Path, version: int, *, dry_run: bool) -> None:
    """Record the layout version in STATUS.md frontmatter."""
    if dry_run:
        return
    from agent_knowledge.runtime.refresh import _fm_set

    path = _status_path(repo_root)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    path.write_text(_fm_set(text, "layout_version", str(version)), encoding="utf-8")
