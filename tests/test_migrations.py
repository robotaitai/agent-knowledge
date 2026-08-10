"""Verify layout version reads and writes against STATUS.md frontmatter."""

from __future__ import annotations

from pathlib import Path

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
