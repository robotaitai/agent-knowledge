"""Verify layout version reads and writes against STATUS.md frontmatter."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_knowledge.runtime import migrations


def _vault(
    tmp_path: Path,
    *,
    layout: str | None = None,
    body: str = "",
    frontmatter: bool = True,
) -> Path:
    """A minimal repo with a bedrock/STATUS.md, optionally carrying a layout_version."""
    repo = tmp_path / "repo"
    (repo / "bedrock").mkdir(parents=True)
    lines: list[str] = []
    if frontmatter:
        lines += ["---", "note_type: knowledge-status", "project: demo"]
        if layout is not None:
            lines.append(f"layout_version: {layout}")
        lines.append("---")
    lines += ["", "# Status", "", body]
    (repo / "bedrock" / "STATUS.md").write_text("\n".join(lines), encoding="utf-8")
    return repo


# --------------------------------------------------------------------------- #
# Reading                                                                      #
# --------------------------------------------------------------------------- #


def test_missing_layout_version_reads_as_zero(tmp_path: Path):
    """A vault predating the registry is layout 0, so every migration is pending."""
    assert migrations.read_layout_version(_vault(tmp_path)) == 0


def test_unparsable_layout_version_reads_as_zero(tmp_path: Path):
    """A hand-mangled value must degrade to 'migrate me', never crash the hook."""
    assert migrations.read_layout_version(_vault(tmp_path, layout="not-a-number")) == 0


def test_missing_status_file_reads_as_zero(tmp_path: Path):
    """An uninitialized repo must not raise."""
    repo = tmp_path / "empty"
    repo.mkdir()
    assert migrations.read_layout_version(repo) == 0


def test_layout_version_in_the_body_is_ignored(tmp_path: Path):
    """Only frontmatter counts, since that is the only place stamping writes."""
    repo = _vault(tmp_path, body="Fields recorded here:\n\nlayout_version: 7\n")
    assert migrations.read_layout_version(repo) == 0


def test_inline_comment_is_stripped(tmp_path: Path):
    """YAML would read this as 2; so must we."""
    repo = _vault(tmp_path, layout="2  # bumped in v0.5")
    assert migrations.read_layout_version(repo) == 2


def test_negative_layout_version_clamps_to_zero(tmp_path: Path):
    """A negative sorts below every migration and would replay the whole registry."""
    assert migrations.read_layout_version(_vault(tmp_path, layout="-3")) == 0


# --------------------------------------------------------------------------- #
# Stamping                                                                     #
# --------------------------------------------------------------------------- #


def test_layout_version_round_trips(tmp_path: Path):
    """Stamping then reading must return what was written."""
    repo = _vault(tmp_path)
    assert migrations.stamp_layout_version(repo, 3, dry_run=False) is True
    assert migrations.read_layout_version(repo) == 3


def test_stamp_replaces_rather_than_appends(tmp_path: Path):
    """Restamping must rewrite the existing key, not accumulate duplicate lines."""
    repo = _vault(tmp_path)
    migrations.stamp_layout_version(repo, 2, dry_run=False)
    migrations.stamp_layout_version(repo, 5, dry_run=False)
    text = (repo / "bedrock" / "STATUS.md").read_text(encoding="utf-8")
    assert text.count("layout_version:") == 1
    assert migrations.read_layout_version(repo) == 5


def test_stamp_is_a_no_op_under_dry_run(tmp_path: Path):
    """--dry-run must not touch STATUS.md."""
    repo = _vault(tmp_path, layout="1")
    migrations.stamp_layout_version(repo, 9, dry_run=True)
    assert migrations.read_layout_version(repo) == 1


def test_stamping_an_already_current_version_writes_nothing(tmp_path: Path):
    """refresh.py promises an up-to-date project writes no files."""
    repo = _vault(tmp_path, layout="4")
    path = repo / "bedrock" / "STATUS.md"
    before = path.read_bytes()
    assert migrations.stamp_layout_version(repo, 4, dry_run=False) is True
    assert path.read_bytes() == before


def test_stamp_reports_failure_without_frontmatter(tmp_path: Path):
    """A silent no-op here would make the runner replay migrations every session."""
    repo = _vault(tmp_path, frontmatter=False)
    assert migrations.stamp_layout_version(repo, 1, dry_run=False) is False


def test_stamp_reports_failure_when_status_is_missing(tmp_path: Path):
    """An uninitialized repo cannot record a version, and must say so."""
    repo = tmp_path / "empty"
    repo.mkdir()
    assert migrations.stamp_layout_version(repo, 1, dry_run=False) is False


def test_stamp_reports_failure_when_status_is_unreadable(tmp_path: Path):
    """A STATUS.md that cannot be read is a failure, not a success."""
    repo = tmp_path / "repo"
    (repo / "bedrock" / "STATUS.md").mkdir(parents=True)
    assert migrations.stamp_layout_version(repo, 1, dry_run=False) is False


# --------------------------------------------------------------------------- #
# Running                                                                      #
# --------------------------------------------------------------------------- #


def test_pending_returns_only_migrations_above_the_recorded_version(tmp_path: Path):
    """A project at layout 1 must not re-run migration 1."""
    calls = []
    registry = (
        migrations.Migration(1, "first", lambda repo, dry_run: calls.append(1)),
        migrations.Migration(2, "second", lambda repo, dry_run: calls.append(2)),
        migrations.Migration(3, "third", lambda repo, dry_run: calls.append(3)),
    )
    repo = _vault(tmp_path, layout="1")

    run = migrations.run_migrations(repo, dry_run=False, registry=registry, target=3)

    assert calls == [2, 3], "only migrations above the recorded version may run"
    assert [m.name for m in run.applied] == ["second", "third"]


def test_migrations_run_in_ascending_order(tmp_path: Path):
    """Order is the whole contract: migration 3 may depend on 2 having run."""
    calls = []
    registry = (
        migrations.Migration(3, "third", lambda repo, dry_run: calls.append(3)),
        migrations.Migration(1, "first", lambda repo, dry_run: calls.append(1)),
        migrations.Migration(2, "second", lambda repo, dry_run: calls.append(2)),
    )

    migrations.run_migrations(_vault(tmp_path), dry_run=False, registry=registry, target=3)

    assert calls == [1, 2, 3]


def test_runner_stamps_the_target_version(tmp_path: Path):
    """After migrating, the project must not migrate again on the next session."""
    registry = (migrations.Migration(1, "first", lambda repo, dry_run: None),)
    repo = _vault(tmp_path)

    migrations.run_migrations(repo, dry_run=False, registry=registry, target=1)

    assert migrations.read_layout_version(repo) == 1


def test_dry_run_passes_the_flag_and_does_not_stamp(tmp_path: Path):
    """--dry-run must report the plan without touching the vault."""
    calls = []
    registry = (migrations.Migration(1, "first", lambda repo, dry_run: calls.append(dry_run)),)
    repo = _vault(tmp_path)

    run = migrations.run_migrations(repo, dry_run=True, registry=registry, target=1)

    assert [m.name for m in run.applied] == ["first"], "the plan must still be reported"
    assert calls == [True], "the migration must be told it is a dry run"
    assert migrations.read_layout_version(repo) == 0, "dry-run must not stamp"


def test_up_to_date_project_runs_nothing(tmp_path: Path):
    """The common case: no work, no write."""
    calls = []
    registry = (migrations.Migration(1, "first", lambda repo, dry_run: calls.append(1)),)
    repo = _vault(tmp_path, layout="1")

    assert migrations.run_migrations(repo, dry_run=False, registry=registry, target=1).applied == []
    assert calls == []


def test_version_advances_even_when_no_migration_is_pending(tmp_path: Path):
    """A layout bump with nothing to do must still be recorded, or it never sticks."""
    repo = _vault(tmp_path)

    run = migrations.run_migrations(repo, dry_run=False, registry=(), target=1)

    assert run.applied == []
    assert run.stamped is True
    assert migrations.read_layout_version(repo) == 1


def test_unstampable_vault_reports_the_failure(tmp_path: Path):
    """A vault with no frontmatter cannot record the stamp, and replays next session.

    Idempotence is what makes that safe, so the runner reports the work it did
    rather than raising out of the SessionStart hook -- but it must say the
    stamp did not land, so refresh.py has something to warn about.
    """
    calls = []
    registry = (migrations.Migration(1, "first", lambda repo, dry_run: calls.append(1)),)
    repo = _vault(tmp_path, frontmatter=False)

    run = migrations.run_migrations(repo, dry_run=False, registry=registry, target=1)

    assert [m.name for m in run.applied] == ["first"]
    assert calls == [1]
    assert run.stamped is False
    assert migrations.read_layout_version(repo) == 0


def test_a_failing_migration_leaves_the_stamp_unwritten(tmp_path: Path):
    """The chain must replay next session, so the stamp may not run early."""

    def boom(repo, dry_run):
        raise RuntimeError("boom")

    registry = (migrations.Migration(1, "first", boom),)
    repo = _vault(tmp_path)

    with pytest.raises(RuntimeError):
        migrations.run_migrations(repo, dry_run=False, registry=registry, target=1)

    assert migrations.read_layout_version(repo) == 0


def test_the_shipped_registry_is_a_no_op_on_an_unstamped_vault(tmp_path: Path):
    """No layout migration exists yet, so a real run must touch nothing at all.

    In particular it must not stamp: a project left unstamped is what makes the
    first real migration run everywhere the day LAYOUT_VERSION is bumped.
    """
    repo = _vault(tmp_path)
    before = (repo / "bedrock" / "STATUS.md").read_text()

    run = migrations.run_migrations(repo, dry_run=False)

    assert run.applied == []
    assert run.stamped is True
    assert (repo / "bedrock" / "STATUS.md").read_text() == before


def test_registry_versions_are_unique_and_cover_the_layout_version():
    """A duplicate or skipped version silently breaks ordering."""
    # Trivially true at LAYOUT_VERSION 0; load-bearing the moment someone bumps it.
    versions = [m.version for m in migrations.MIGRATIONS]
    assert versions == sorted(set(versions)), "versions must be unique and ordered"
    assert versions == list(range(1, migrations.LAYOUT_VERSION + 1)), (
        "every layout version from 1 to LAYOUT_VERSION needs exactly one migration"
    )


# --------------------------------------------------------------------------- #
# Wiring into refresh-system                                                   #
# --------------------------------------------------------------------------- #


def test_refresh_refuses_to_downgrade_a_newer_project(tmp_path: Path):
    """An older CLI must never rewrite a newer project's files.

    refresh-system runs from the SessionStart hook, so without this a teammate
    on an older bedrock reverts the layout on every single session.
    """
    from agent_knowledge.runtime.refresh import run_refresh

    repo = _vault(tmp_path, layout=str(migrations.LAYOUT_VERSION + 1))
    project_yaml = repo / ".agent-project.yaml"
    project_yaml.write_text('framework_version: "0.0.1"\n', encoding="utf-8")

    result = run_refresh(repo, dry_run=False)

    assert result["action"] == "blocked"
    assert result["layout_version"] == migrations.LAYOUT_VERSION
    assert result["project_layout_version"] == migrations.LAYOUT_VERSION + 1
    assert any("pip install -U project-bedrock" in w for w in result["warnings"])
    assert '"0.0.1"' in project_yaml.read_text(), "a blocked refresh must write nothing at all"


def test_refresh_reports_applied_migrations(tmp_path: Path, monkeypatch):
    """Applied migrations must show up as changes so the user can see what happened."""
    from agent_knowledge.runtime.refresh import run_refresh

    seen = []
    monkeypatch.setattr(migrations, "LAYOUT_VERSION", 1)
    monkeypatch.setattr(
        migrations,
        "MIGRATIONS",
        (migrations.Migration(1, "demo step", lambda repo, dry_run: seen.append(repo)),),
    )

    repo = _vault(tmp_path)
    result = run_refresh(repo, dry_run=False)

    assert seen, "the migration must actually run"
    details = [c["detail"] for c in result["changes"] if c["target"] == "layout migration"]
    assert details == ["1: demo step"]
    assert migrations.read_layout_version(repo) == 1


def test_refresh_survives_a_failing_migration(tmp_path: Path, monkeypatch):
    """One bad migration must not take down the whole refresh or the session."""
    from agent_knowledge.runtime.refresh import run_refresh

    def boom(repo, dry_run):
        raise RuntimeError("boom")

    monkeypatch.setattr(migrations, "LAYOUT_VERSION", 1)
    monkeypatch.setattr(migrations, "MIGRATIONS", (migrations.Migration(1, "bad step", boom),))

    repo = _vault(tmp_path)
    result = run_refresh(repo, dry_run=False)

    assert any("boom" in w for w in result["warnings"]), "the failure must be reported"
    assert any(c["action"] == "failed" for c in result["changes"])
    assert migrations.read_layout_version(repo) == 0, "a failed chain must not stamp"


def test_refresh_warns_when_the_layout_version_cannot_be_recorded(tmp_path: Path, monkeypatch):
    """A vault that cannot be stamped replays forever; that must not be silent."""
    from agent_knowledge.runtime.refresh import run_refresh

    monkeypatch.setattr(migrations, "LAYOUT_VERSION", 1)
    monkeypatch.setattr(
        migrations,
        "MIGRATIONS",
        (migrations.Migration(1, "demo step", lambda repo, dry_run: None),),
    )

    repo = _vault(tmp_path)
    # A STATUS.md with no frontmatter cannot carry the stamp.
    (repo / "bedrock" / "STATUS.md").write_text("# Status\n", encoding="utf-8")

    result = run_refresh(repo, dry_run=False)

    assert any("replay" in w for w in result["warnings"])


def test_refresh_at_the_same_layout_reports_both_versions(tmp_path: Path):
    """The normal path must still report the versions for doctor and the CLI."""
    from agent_knowledge.runtime.refresh import run_refresh

    repo = _vault(tmp_path)
    result = run_refresh(repo, dry_run=False)

    assert result["layout_version"] == migrations.LAYOUT_VERSION
    assert result["project_layout_version"] == migrations.LAYOUT_VERSION
    assert result["action"] != "blocked"
