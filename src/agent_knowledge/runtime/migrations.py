"""Ordered, idempotent migrations for the on-disk vault layout.

The package version and the layout version are deliberately separate. Most
releases change no on-disk format and leave LAYOUT_VERSION alone; bumping it is
an explicit act that says "an existing project needs work done to it".

What belongs here, and what does not. A migration is for a one-time,
irreversible change to the on-disk layout. It is not for a value that other
writers can regress -- an older CLI on a teammate's machine, or a bad merge.
Those need an unconditional repair on every refresh, as `_refresh_gitignore` and
the hook-command merge do, because a version stamp would wrongly declare them
permanently fixed. STATUS.md is git-tracked, so the stamp travels to every clone
and silences the repair everywhere at once.

Failure handling is split. Reads degrade and a failed stamp is reported rather
than raised, because this runs from the SessionStart hook. A failing *migration*
is different: it propagates, stopping the chain with the stamp unwritten, so the
next session replays from the last good version. Continuing past it would run
migration N+1 against a vault that never finished N. `refresh.py` owns the
try/except around this call, so one bad migration cannot take down a refresh.

That asymmetry constrains how a migration reads files. Catch FileNotFoundError
when absence is legitimately nothing to do, and let every other OSError
propagate. A blanket `except OSError: return` conflates "no file" with "cannot
read it right now" and the chain stamps anyway, so the repair never retries.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, NamedTuple, Sequence

from agent_knowledge.runtime.frontmatter import fm_get, fm_set

# Bump only when the on-disk layout changes, and add a Migration for it.
#
# Before the first bump, check that the release carrying this module is widely
# deployed. The downgrade guard in refresh.py only protects from that release
# forward: an install at 0.4.17 or earlier has no layout version to compare and
# will happily revert a newer project's layout from its SessionStart hook. Bump
# too early and the guard protects nobody on the teams that most need it.
LAYOUT_VERSION = 0


class Migration(NamedTuple):
    """One irreversible step to layout `version`, applied in ascending order.

    `apply` must be safe to re-run and safe to resume after partial application.
    A crash leaves the stamp unwritten, so the whole chain re-runs next session --
    including the migration that crashed, from wherever it got to. Re-running a
    completed migration and finishing a half-done one are both required.
    """

    version: int
    name: str
    apply: Callable[[Path, bool], None]


class MigrationRun(NamedTuple):
    """What a run did, and whether the result was recorded.

    `stamped` is False when the version could not be written, which means the
    work replays next session. Harmless but invisible, so the caller reports it.
    """

    applied: list[Migration]
    stamped: bool


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
) -> MigrationRun:
    """Apply every migration above the project's recorded version, in order.

    Reports the migrations applied (or, under dry_run, that would be) and whether
    the new version was recorded. Raises whatever a migration raises. `registry`
    and `target` are injectable so the ordering contract can be tested without
    inventing real layout versions.
    """
    registry = MIGRATIONS if registry is None else registry
    target = LAYOUT_VERSION if target is None else target

    current = read_layout_version(repo_root)
    pending = sorted(
        (m for m in registry if current < m.version <= target),
        key=lambda m: m.version,
    )

    # Stamping after applying is what makes a crash replay rather than skip.
    for migration in pending:
        migration.apply(repo_root, dry_run)

    # Stamps `target`, not the highest applied version: correct only because
    # LAYOUT_VERSION is bumped in lockstep with adding a migration, so a version
    # with no migration of its own still needs recording.
    # `current < target` also prevents stamping a downgrade.
    if current < target:
        stamped = stamp_layout_version(repo_root, target, dry_run=dry_run)
    else:
        stamped = True
    return MigrationRun(applied=pending, stamped=stamped)


# No layout migration exists yet. The mechanism above is deliberately shipped
# empty: LAYOUT_VERSION stays 0 until a real on-disk layout change needs one.
MIGRATIONS: tuple[Migration, ...] = ()
