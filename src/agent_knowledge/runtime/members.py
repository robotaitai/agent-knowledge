"""Per-member context: distinct "minds" plus shared team consensus.

Two additive folders under the vault's ``Memory/``, orthogonal to the existing
by-purpose layers (Memory/History/Evidence/...):

    Memory/Team/            shared, normalized consensus (canonical team truth)
    Memory/Members/<id>/    one folder per member (person or agent) — their own
                            perspective notes. Conflict-free in git because each
                            member edits only their own folder.

Identity resolution ("who am I") precedence:

    1. BEDROCK_MEMBER environment variable
    2. .bedrock/member file (per-machine, gitignored — `bedrock member use`)
    3. slug of `git config user.name`
    4. None (unset)

Member folders are committed (that is the transparency: each member's stance is
legible to the team and the lead). Only the *pointer* to the current member
(``.bedrock/``) is per-machine and gitignored.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def members_root(vault: Path) -> Path:
    """Return ``Memory/Members`` for the given vault directory."""
    return vault / "Memory" / "Members"


def team_root(vault: Path) -> Path:
    """Return ``Memory/Team`` for the given vault directory."""
    return vault / "Memory" / "Team"


def current_member_file(repo: Path) -> Path:
    """Return the per-machine current-member pointer (``.bedrock/member``)."""
    return repo / ".bedrock" / "member"


# ---------------------------------------------------------------------------
# Slugging
# ---------------------------------------------------------------------------


def slugify(name: str) -> str:
    """Normalize a member name into a filesystem- and git-friendly slug.

    Lowercase, spaces/underscores -> hyphen, drop anything outside [a-z0-9-],
    collapse repeats, strip leading/trailing hyphens. Returns "" for empty input.
    """
    text = (name or "").strip().lower()
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"[^a-z0-9-]+", "", text)
    text = re.sub(r"-{2,}", "-", text)
    return text.strip("-")


# ---------------------------------------------------------------------------
# Identity resolution
# ---------------------------------------------------------------------------


def _git_user_name(repo: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "config", "user.name"],
            capture_output=True,
            text=True,
            cwd=str(repo),
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    name = result.stdout.strip()
    return name or None


def resolve_member(repo: Path) -> str | None:
    """Resolve the current member slug by precedence. Returns None if unset."""
    env = os.environ.get("BEDROCK_MEMBER")
    if env and slugify(env):
        return slugify(env)

    pointer = current_member_file(repo)
    if pointer.is_file():
        slug = slugify(pointer.read_text(encoding="utf-8"))
        if slug:
            return slug

    git_name = _git_user_name(repo)
    if git_name:
        slug = slugify(git_name)
        if slug:
            return slug

    return None


def set_current_member(repo: Path, name: str) -> str:
    """Persist the current member for this machine. Returns the stored slug.

    Writes ``.bedrock/member`` and a ``.bedrock/.gitignore`` that keeps the whole
    per-machine state out of git.
    """
    slug = slugify(name)
    if not slug:
        raise ValueError(f"Invalid member name: {name!r}")
    dot = repo / ".bedrock"
    dot.mkdir(parents=True, exist_ok=True)
    gitignore = dot / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("# per-machine bedrock state; not shared\n*\n", encoding="utf-8")
    current_member_file(repo).write_text(slug + "\n", encoding="utf-8")
    return slug


# ---------------------------------------------------------------------------
# Templates (kept inline so the feature has no asset-packaging dependency)
# ---------------------------------------------------------------------------

# Branch entry notes. bedrock treats each direct subfolder of Memory/ as a branch
# that needs a same-name entry note (<branch>/<branch>.md) with YAML frontmatter;
# note_type: memory-branch requires the five standard sections. Conforming here
# keeps the scaffold clean under `bedrock validate` and `bedrock doctor`.

_MEMBERS_ENTRY = """\
---
note_type: memory-branch
area: members
title: Members — distinct minds
---

# Members — distinct minds

## Purpose

One folder per team member (a person or an agent). Each member curates **only
their own** `Members/<id>/` folder, so people never collide in git and each
member's perspective is preserved rather than flattened.

## Current State

- Add a member: `bedrock member add <name>` (use `--kind agent` for agents).
- See who exists: `bedrock member list`.
- Tell bedrock who you are: `bedrock member use <name>` (or set `BEDROCK_MEMBER`).

## Recent Changes

- Branch created.

## Decisions

- Member folders are committed on purpose: each person's stance is legible to the
  team and the team lead. Normalized agreements graduate into `../Team/`.

## Open Questions

- (none yet)
"""

_TEAM_ENTRY = """\
---
note_type: memory-branch
area: team
title: Team — shared consensus
---

# Team — shared consensus

## Purpose

Normalized, agreed-upon knowledge the team has converged on through managed
dialogue. This is **canonical team truth** — the same trust level as the rest of
`Memory/`.

## Current State

Individual perspectives live in `../Members/<id>/`. When a position is agreed, it
graduates here as shared consensus.

## Recent Changes

- Branch created.

## Decisions

- Record agreed team decisions here (or link to `../decisions/`).

## Open Questions

- Disagreements currently being worked through the dialogue.
"""

_PROFILE_TEMPLATE = """\
---
note_type: member-profile
member: {slug}
name: {name}
kind: {kind}
role: {role}
created: {date}
---

# {name}

- **Role:** {role}
- **Kind:** {kind}

## Perspective

How {name} approaches this project — priorities, strong opinions, biases, the
lenses they bring. Keep this current; it is what makes this a distinct "mind."

## Positions

Stances on open questions and decisions. When a position becomes a team agreement,
move it into `../../Team/`.
"""

_NOTES_TEMPLATE = """\
---
note_type: member-notes
member: {slug}
created: {date}
---

# {name} — working notes

{name}'s own context for this project. You own this file; edit freely without
worrying about conflicting with teammates.
"""


def _today() -> str:
    import datetime

    return datetime.date.today().isoformat()


# ---------------------------------------------------------------------------
# Scaffolding + members
# ---------------------------------------------------------------------------


def ensure_scaffold(vault: Path, *, dry_run: bool = False) -> list[str]:
    """Ensure ``Memory/Team`` and ``Memory/Members`` exist with branch entry notes.

    Writes ``Team/Team.md`` and ``Members/Members.md`` (frontmatter'd branch entry
    notes, per bedrock's same-name-branch convention) so the scaffold stays clean
    under ``bedrock validate`` / ``doctor``. Idempotent. Returns the relative paths
    created (empty if already set up).
    """
    created: list[str] = []
    targets = [
        (team_root(vault), "Team.md", _TEAM_ENTRY, "Memory/Team/Team.md"),
        (members_root(vault), "Members.md", _MEMBERS_ENTRY, "Memory/Members/Members.md"),
    ]
    for directory, entry_name, body, rel in targets:
        entry_path = directory / entry_name
        if entry_path.exists():
            continue
        if not dry_run:
            directory.mkdir(parents=True, exist_ok=True)
            entry_path.write_text(body, encoding="utf-8")
        created.append(rel)
    return created


def add_member(
    vault: Path,
    name: str,
    *,
    role: str | None = None,
    kind: str = "person",
    force: bool = False,
) -> dict:
    """Create a member folder with PROFILE.md and notes.md.

    Idempotent: existing files are left untouched unless ``force`` is set.
    Returns ``{"slug", "name", "path", "created": [...]}``.
    """
    slug = slugify(name)
    if not slug:
        raise ValueError(f"Invalid member name: {name!r}")
    if kind not in ("person", "agent"):
        raise ValueError(f"kind must be 'person' or 'agent', got {kind!r}")

    created = ensure_scaffold(vault)

    member_dir = members_root(vault) / slug
    member_dir.mkdir(parents=True, exist_ok=True)

    fields = {
        "slug": slug,
        "name": name.strip(),
        "kind": kind,
        "role": role or "TBD",
        "date": _today(),
    }
    files = [
        (member_dir / "PROFILE.md", _PROFILE_TEMPLATE),
        (member_dir / "notes.md", _NOTES_TEMPLATE),
    ]
    for path, template in files:
        rel = path.relative_to(vault).as_posix()
        if path.exists() and not force:
            continue
        path.write_text(template.format(**fields), encoding="utf-8")
        created.append(f"Memory/{rel}" if not rel.startswith("Memory/") else rel)

    return {
        "slug": slug,
        "name": fields["name"],
        "path": str(member_dir),
        "created": created,
    }


def _read_frontmatter(path: Path) -> dict:
    """Parse a leading ``--- ... ---`` YAML-ish block into a flat dict."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    if not text.startswith("---"):
        return {}
    lines = text.splitlines()
    fields: dict = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" in line:
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
    return fields


def list_members(vault: Path) -> list[dict]:
    """Return one record per member folder, sorted by slug."""
    root = members_root(vault)
    if not root.is_dir():
        return []
    members: list[dict] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        profile = child / "PROFILE.md"
        fm = _read_frontmatter(profile) if profile.exists() else {}
        notes_count = sum(1 for _ in child.glob("*.md"))
        members.append(
            {
                "slug": child.name,
                "name": fm.get("name", child.name),
                "kind": fm.get("kind", "person"),
                "role": fm.get("role", "TBD"),
                "has_profile": profile.exists(),
                "notes": notes_count,
            }
        )
    return members
