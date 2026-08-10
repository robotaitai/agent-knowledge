"""Verify the layout migration registry: versioning, ordering, idempotence."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_knowledge.runtime import migrations


def _vault(tmp_path: Path, *, layout: str | None = None) -> Path:
    """A minimal repo with a bedrock/STATUS.md, optionally carrying a layout_version."""
    repo = tmp_path / "repo"
    (repo / "bedrock").mkdir(parents=True)
    lines = ["---", "note_type: knowledge-status", "project: demo"]
    if layout is not None:
        lines.append(f"layout_version: {layout}")
    lines += ["---", "", "# Status", ""]
    (repo / "bedrock" / "STATUS.md").write_text("\n".join(lines), encoding="utf-8")
    return repo


def test_missing_layout_version_reads_as_zero(tmp_path: Path):
    """A vault predating the registry is layout 0, so every migration is pending."""
    assert migrations.read_layout_version(_vault(tmp_path)) == 0


def test_layout_version_round_trips(tmp_path: Path):
    """Stamping then reading must return what was written."""
    repo = _vault(tmp_path)
    migrations.stamp_layout_version(repo, 3, dry_run=False)
    assert migrations.read_layout_version(repo) == 3


def test_stamp_is_a_no_op_under_dry_run(tmp_path: Path):
    """--dry-run must not touch STATUS.md."""
    repo = _vault(tmp_path, layout="1")
    migrations.stamp_layout_version(repo, 9, dry_run=True)
    assert migrations.read_layout_version(repo) == 1


def test_unparsable_layout_version_reads_as_zero(tmp_path: Path):
    """A hand-mangled value must degrade to 'migrate me', never crash the hook."""
    assert migrations.read_layout_version(_vault(tmp_path, layout="not-a-number")) == 0


def test_missing_status_file_reads_as_zero(tmp_path: Path):
    """An uninitialized repo must not raise."""
    repo = tmp_path / "empty"
    repo.mkdir()
    assert migrations.read_layout_version(repo) == 0
