"""Ordered, idempotent migrations for the on-disk vault layout.

The package version and the layout version are deliberately separate. Most
releases change no on-disk format and leave LAYOUT_VERSION alone; bumping it is
an explicit act that says "an existing project needs work done to it".
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, NamedTuple, Sequence

from agent_knowledge.runtime.frontmatter import fm_get, fm_set

# Bump only when the on-disk layout changes, and add a Migration for it.
LAYOUT_VERSION = 1


class Migration(NamedTuple):
    """One irreversible step from layout `version - 1` to `version`.

    `apply` must be idempotent: it runs from the SessionStart hook, and a crash
    partway through a chain leaves the stamp unwritten, so the whole chain
    re-runs on the next session.
    """

    version: int
    name: str
    apply: Callable[[Path, bool], None]


def _status_path(repo_root: Path) -> Path:
    return repo_root / "bedrock" / "STATUS.md"


def _read_status(repo_root: Path) -> str | None:
    """STATUS.md's text, or None when it cannot be read."""
    try:
        return _status_path(repo_root).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def read_layout_version(repo_root: Path) -> int:
    """The project's recorded layout version, or 0 when absent, malformed, or unreadable.

    Degrading to 0 rather than raising matters: this runs from the SessionStart
    hook, where an exception would surface as a broken agent session. Collapsing
    "corrupt" into "absent" is deliberate rather than an oversight — migrations
    are required to be idempotent, so replaying them is safe.

    Only frontmatter is consulted, because that is the only place stamping
    writes; a layout_version line in the prose body is documentation, not state.
    """
    text = _read_status(repo_root)
    if text is None:
        return 0
    raw = fm_get(text, "layout_version").split("#", 1)[0].strip()
    try:
        value = int(raw)
    except ValueError:
        return 0
    # A negative sorts below every migration and would replay the whole registry.
    return max(value, 0)


def stamp_layout_version(repo_root: Path, version: int, *, dry_run: bool) -> bool:
    """Record the layout version in STATUS.md frontmatter.

    Returns True when the version is recorded, False when it could not be. The
    caller stamps after applying migrations, so a silent failure here would make
    every session replay the whole chain. Under dry_run nothing is written and
    the return value reports what a real run would have managed.
    """
    text = _read_status(repo_root)
    if text is None:
        return False
    updated = fm_set(text, "layout_version", str(version))
    if updated == text:
        # Either already current, or there is no frontmatter for fm_set to touch.
        return read_layout_version(repo_root) == version
    if dry_run:
        return True
    _status_path(repo_root).write_text(updated, encoding="utf-8")
    return True


def run_migrations(
    repo_root: Path,
    *,
    dry_run: bool,
    registry: Sequence[Migration] | None = None,
    target: int | None = None,
) -> list[Migration]:
    """Apply every migration above the project's recorded version, in order.

    Returns the migrations that were applied (or, under dry_run, would be).
    `registry` and `target` are injectable so the ordering contract can be
    tested without inventing real layout versions.
    """
    registry = MIGRATIONS if registry is None else registry
    target = LAYOUT_VERSION if target is None else target

    current = read_layout_version(repo_root)
    pending = sorted(
        (m for m in registry if current < m.version <= target),
        key=lambda m: m.version,
    )
    if not pending:
        return []

    for migration in pending:
        migration.apply(repo_root, dry_run)

    # A failed stamp is deliberately not fatal: migrations are idempotent, so an
    # unstampable vault replays the chain rather than losing work, and raising
    # here would break the agent session this runs from.
    stamp_layout_version(repo_root, target, dry_run=dry_run)
    return pending


MIGRATIONS: tuple[Migration, ...] = ()
