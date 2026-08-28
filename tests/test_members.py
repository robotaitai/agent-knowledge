"""Verify the `bedrock member` group: scaffolding, listing, identity resolution."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

BIN = [sys.executable, "-m", "agent_knowledge"]


def _run(*args: str, **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*BIN, *args],
        capture_output=True,
        text=True,
        timeout=30,
        **kwargs,
    )


def _clean_env(**overrides: str) -> dict:
    """Env without an inherited BEDROCK_MEMBER, plus any overrides."""
    env = dict(os.environ)
    env.pop("BEDROCK_MEMBER", None)
    env.update(overrides)
    return env


def _vault_repo(tmp_path: Path, name: str = "repo", user: str | None = "Test User") -> Path:
    """A repo with an empty ./bedrock vault and (optionally) a local git user."""
    repo = tmp_path / name
    (repo / "bedrock" / "Memory").mkdir(parents=True)
    subprocess.run(["git", "init", str(repo)], capture_output=True)
    if user is not None:
        subprocess.run(["git", "-C", str(repo), "config", "user.name", user], capture_output=True)
    return repo


# -- group + add ----------------------------------------------------------- #


def test_member_group_help():
    r = _run("member", "--help")
    assert r.returncode == 0
    for sub in ("add", "list", "whoami", "use"):
        assert sub in r.stdout


def test_member_add_scaffolds_member_and_layers(tmp_path: Path):
    repo = _vault_repo(tmp_path)
    r = _run("member", "add", "Guy Avraham", "--role", "Lead", "--project", str(repo), "--json")
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["slug"] == "guy-avraham"

    vault = repo / "bedrock"
    assert (vault / "Memory" / "Members" / "guy-avraham" / "PROFILE.md").is_file()
    assert (vault / "Memory" / "Members" / "guy-avraham" / "notes.md").is_file()
    # The Team + Members layers are scaffolded on first add, as frontmatter'd
    # branch entry notes (not READMEs) so they pass `bedrock validate`.
    assert (vault / "Memory" / "Team" / "Team.md").is_file()
    assert (vault / "Memory" / "Members" / "Members.md").is_file()
    # PROFILE carries identifying frontmatter.
    profile = (vault / "Memory" / "Members" / "guy-avraham" / "PROFILE.md").read_text()
    assert "member: guy-avraham" in profile
    assert "role: Lead" in profile


def test_member_add_is_idempotent(tmp_path: Path):
    repo = _vault_repo(tmp_path)
    _run("member", "add", "Dana", "--project", str(repo))
    profile = repo / "bedrock" / "Memory" / "Members" / "dana" / "PROFILE.md"
    profile.write_text(profile.read_text() + "\nedited-by-hand\n")

    r = _run("member", "add", "Dana", "--project", str(repo), "--json")
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    # PROFILE/notes already existed, so nothing about them is reported as created.
    assert not any("PROFILE.md" in c for c in data["created"])
    # And the hand edit survives (no overwrite without --force).
    assert "edited-by-hand" in profile.read_text()


def test_member_add_rejects_empty_slug(tmp_path: Path):
    repo = _vault_repo(tmp_path)
    r = _run("member", "add", "***", "--project", str(repo))
    assert r.returncode == 1
    assert "Invalid member name" in r.stderr


def test_member_add_requires_vault(tmp_path: Path):
    repo = tmp_path / "no-vault"
    repo.mkdir()
    r = _run("member", "add", "Guy", "--project", str(repo))
    assert r.returncode == 1
    assert "No bedrock vault" in r.stderr


# -- list ------------------------------------------------------------------ #


def test_member_list_json(tmp_path: Path):
    repo = _vault_repo(tmp_path)
    _run("member", "add", "Guy", "--role", "Lead", "--project", str(repo))
    _run("member", "add", "Aria", "--kind", "agent", "--project", str(repo))

    r = _run("member", "list", "--project", str(repo), "--json")
    assert r.returncode == 0, r.stderr
    members = {m["slug"]: m for m in json.loads(r.stdout)["members"]}
    assert set(members) == {"guy", "aria"}
    assert members["guy"]["role"] == "Lead"
    assert members["aria"]["kind"] == "agent"


# -- whoami / use ---------------------------------------------------------- #


def test_whoami_env_takes_precedence(tmp_path: Path):
    repo = _vault_repo(tmp_path, user="Git Person")
    r = _run(
        "member", "whoami", "--project", str(repo),
        env=_clean_env(BEDROCK_MEMBER="Env Person"),
    )
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "env-person"


def test_whoami_falls_back_to_git_user(tmp_path: Path):
    repo = _vault_repo(tmp_path, user="Git Person")
    r = _run("member", "whoami", "--project", str(repo), env=_clean_env())
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "git-person"


def test_use_writes_pointer_and_overrides_git(tmp_path: Path):
    repo = _vault_repo(tmp_path, user="Git Person")
    ru = _run("member", "use", "Pointer Person", "--project", str(repo), env=_clean_env())
    assert ru.returncode == 0, ru.stderr

    assert (repo / ".bedrock" / "member").read_text().strip() == "pointer-person"
    # Per-machine state is kept out of git.
    assert "*" in (repo / ".bedrock" / ".gitignore").read_text()

    rw = _run("member", "whoami", "--project", str(repo), env=_clean_env())
    assert rw.stdout.strip() == "pointer-person"


def test_whoami_unset_exits_nonzero(tmp_path: Path):
    repo = _vault_repo(tmp_path, user=None)
    # Isolate from any global/system git identity so resolution is truly empty.
    env = _clean_env(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)
    r = _run("member", "whoami", "--project", str(repo), env=env)
    assert r.returncode == 1
    assert "no member set" in r.stderr


# -- index integration ----------------------------------------------------- #


def test_member_notes_are_non_canonical_but_team_is(tmp_path: Path):
    """A member's perspective must not be indexed as canonical team truth."""
    from agent_knowledge.runtime.index import build_index

    repo = _vault_repo(tmp_path)
    _run("member", "add", "Guy", "--project", str(repo))
    vault = repo / "bedrock"
    (vault / "Memory" / "Team" / "shared-decision.md").write_text(
        "---\nnote_type: decision\n---\n# Shared decision\nWe agreed on X.\n",
        encoding="utf-8",
    )

    by_path = {n["path"]: n for n in build_index(vault)["notes"]}

    # A member's own note + the Members branch entry: perspective, not canon.
    member_note = by_path["Memory/Members/guy/PROFILE.md"]
    assert member_note["canonical"] is False
    assert member_note["folder"] == "Members"
    assert by_path["Memory/Members/Members.md"]["canonical"] is False

    # Team consensus (entry note + a decision): canonical.
    assert by_path["Memory/Team/Team.md"]["canonical"] is True
    team_note = by_path["Memory/Team/shared-decision.md"]
    assert team_note["canonical"] is True
    assert team_note["folder"] == "Memory"


def test_scaffold_passes_bedrock_validate(tmp_path: Path):
    """Adding a member must not introduce validate/doctor complaints about the
    new Memory/Members and Memory/Team branches (frontmatter + entry notes)."""
    repo = _vault_repo(tmp_path)
    # Minimal valid vault so `validate` runs: it needs STATUS.md + a decisions log.
    vault = repo / "bedrock"
    (vault / "STATUS.md").write_text("---\nframework_version: 0\n---\n# STATUS\n", encoding="utf-8")

    _run("member", "add", "Guy", "--project", str(repo))

    r = _run("validate", "--project", str(repo))
    out = r.stdout + r.stderr
    offenders = [l for l in out.splitlines() if "Members/" in l or "/Team/" in l or "Team.md" in l]
    assert offenders == [], "validate complained about member/team scaffold:\n" + "\n".join(offenders)
