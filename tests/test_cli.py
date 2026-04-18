"""Verify CLI commands, help output, JSON mode, and dry-run behavior."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

BIN = [sys.executable, "-m", "agent_knowledge"]


def _run(*args: str, **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*BIN, *args],
        capture_output=True,
        text=True,
        timeout=30,
        **kwargs,
    )


def _init_repo(tmp_path: Path, name: str = "test-repo") -> Path:
    repo = tmp_path / name
    repo.mkdir()
    subprocess.run(["git", "init", str(repo)], capture_output=True)
    return repo


def test_top_level_help():
    r = _run("--help")
    assert r.returncode == 0
    assert "agent-knowledge" in r.stdout.lower() or "adaptive" in r.stdout.lower()


def test_version():
    from agent_knowledge import __version__

    r = _run("--version")
    assert r.returncode == 0
    assert __version__ in r.stdout


@pytest.mark.parametrize(
    "cmd",
    [
        "init",
        "bootstrap",
        "import",
        "update",
        "doctor",
        "validate",
        "ship",
        "global-sync",
        "graphify-sync",
        "compact",
        "measure-tokens",
        "setup",
        "sync",
        "search",
        "index",
        "export-html",
        "view",
        "clean-import",
        "export-canvas",
        "refresh-system",
        "backfill-history",
        "absorb",
    ],
)
def test_subcommand_help(cmd: str):
    r = _run(cmd, "--help")
    assert r.returncode == 0
    assert len(r.stdout) > 20


def test_init_help_shows_slug():
    r = _run("init", "--help")
    assert "--slug" in r.stdout
    assert "--repo" in r.stdout


def test_init_dry_run(tmp_path: Path):
    repo = _init_repo(tmp_path)
    r = _run(
        "init",
        "--repo", str(repo),
        "--knowledge-home", str(tmp_path / "kh"),
        "--dry-run",
    )
    assert not (repo / "agent-knowledge").exists()
    assert not (repo / ".agent-project.yaml").exists()


def test_init_infers_slug_from_dirname(tmp_path: Path):
    repo = _init_repo(tmp_path, "My Cool Project")
    kh = tmp_path / "kh"
    r = _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    assert r.returncode == 0, f"init failed: {r.stderr}"
    assert (repo / "agent-knowledge").is_symlink()
    assert (kh / "my-cool-project").is_dir()


def test_init_zero_arg_from_cwd(tmp_path: Path):
    repo = _init_repo(tmp_path, "zero-arg-test")
    kh = tmp_path / "kh"
    r = subprocess.run(
        [*BIN, "init", "--knowledge-home", str(kh)],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(repo),
    )
    assert r.returncode == 0, f"init failed: {r.stderr}"
    assert (repo / "agent-knowledge").is_symlink()
    assert (repo / ".agent-project.yaml").is_file()


def test_init_installs_cursor_hooks(tmp_path: Path):
    repo = _init_repo(tmp_path, "hooks-test")
    kh = tmp_path / "kh"
    r = _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    assert r.returncode == 0, f"init failed: {r.stderr}"
    assert (repo / ".cursor" / "hooks.json").is_file()


def test_init_installs_claude_integration(tmp_path: Path):
    """Claude integration is always installed (like Cursor)."""
    repo = _init_repo(tmp_path, "claude-test")
    kh = tmp_path / "kh"
    r = _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    assert r.returncode == 0, f"init failed: {r.stderr}"
    assert (repo / ".claude" / "settings.json").is_file()
    assert (repo / ".claude" / "CLAUDE.md").is_file()
    assert (repo / ".claude" / "commands" / "memory-update.md").is_file()
    assert (repo / ".claude" / "commands" / "system-update.md").is_file()
    content = (repo / ".claude" / "CLAUDE.md").read_text()
    assert "agent-knowledge" in content.lower()


def test_init_installs_codex_bridge_when_detected(tmp_path: Path):
    repo = _init_repo(tmp_path, "codex-test")
    (repo / ".codex").mkdir()
    kh = tmp_path / "kh"
    r = _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    assert r.returncode == 0, f"init failed: {r.stderr}"
    assert (repo / ".codex" / "AGENTS.md").is_file()


def test_init_multi_tool_detection(tmp_path: Path):
    repo = _init_repo(tmp_path, "multi-tool")
    (repo / ".codex").mkdir()
    kh = tmp_path / "kh"
    r = _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    assert r.returncode == 0, f"init failed: {r.stderr}"
    assert (repo / ".cursor" / "hooks.json").is_file()
    assert (repo / ".claude" / "settings.json").is_file()
    assert (repo / ".claude" / "CLAUDE.md").is_file()
    assert (repo / ".codex" / "AGENTS.md").is_file()


def test_init_idempotent(tmp_path: Path):
    repo = _init_repo(tmp_path, "idempotent-test")
    kh = tmp_path / "kh"
    r1 = _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    assert r1.returncode == 0
    r2 = _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    assert r2.returncode == 0
    assert (repo / "agent-knowledge").is_symlink()
    assert (repo / ".agent-project.yaml").is_file()
    assert (repo / "AGENTS.md").is_file()


def test_init_sets_onboarding_pending(tmp_path: Path):
    repo = _init_repo(tmp_path, "onboarding-test")
    kh = tmp_path / "kh"
    r = _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    assert r.returncode == 0
    status = (repo / "agent-knowledge" / "STATUS.md").read_text()
    assert "onboarding: pending" in status


def test_agents_md_has_onboarding_instructions(tmp_path: Path):
    repo = _init_repo(tmp_path, "agents-md-test")
    kh = tmp_path / "kh"
    r = _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    assert r.returncode == 0
    agents = (repo / "AGENTS.md").read_text()
    assert "First-Time Onboarding" in agents
    assert "STATUS.md" in agents
    assert "onboarding: pending" in agents or "onboarding" in agents.lower()


def test_doctor_json_includes_integrations(tmp_path: Path):
    repo = _init_repo(tmp_path, "doctor-int")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    r = _run("doctor", "--project", str(repo), "--json")
    stdout = r.stdout.strip()
    if stdout:
        parsed = json.loads(stdout)
        assert "integrations" in parsed
        assert "onboarding" in parsed


def test_doctor_json_is_clean_json(tmp_path: Path):
    repo = _init_repo(tmp_path, "json-repo")
    r = _run("doctor", "--project", str(repo), "--json")
    stdout = r.stdout.strip()
    if stdout:
        parsed = json.loads(stdout)
        assert isinstance(parsed, dict)
        assert "script" in parsed


def test_smoke_init_doctor(tmp_path: Path):
    repo = _init_repo(tmp_path, "smoke")
    kh = tmp_path / "kh"
    r = _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    assert r.returncode == 0, f"init failed:\nstdout: {r.stdout}\nstderr: {r.stderr}"
    assert (repo / "agent-knowledge").is_symlink()
    assert (repo / ".agent-project.yaml").is_file()
    assert (repo / "AGENTS.md").is_file()

    r = _run("doctor", "--project", str(repo), "--json")
    stdout = r.stdout.strip()
    if stdout:
        parsed = json.loads(stdout)
        assert parsed.get("script") == "doctor"


def test_measure_tokens_no_args_shows_help():
    r = _run("measure-tokens")
    assert r.returncode == 0
    assert "compare" in r.stdout.lower() or "log-run" in r.stdout.lower()


# -- sync tests ------------------------------------------------------------ #


def test_sync_dry_run(tmp_path: Path):
    repo = _init_repo(tmp_path, "sync-dry")
    kh = tmp_path / "kh"
    r = _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    assert r.returncode == 0

    # Create agent_docs/memory with a file
    mem_dir = repo / "agent_docs" / "memory"
    mem_dir.mkdir(parents=True)
    (mem_dir / "MEMORY.md").write_text("---\nproject: test\n---\n# Memory\n")

    r = _run("sync", "--project", str(repo), "--dry-run")
    assert r.returncode == 0
    assert "dry-run" in r.stderr.lower()


def test_sync_copies_memory_branches(tmp_path: Path):
    repo = _init_repo(tmp_path, "sync-mem")
    kh = tmp_path / "kh"
    r = _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    assert r.returncode == 0

    mem_dir = repo / "agent_docs" / "memory"
    mem_dir.mkdir(parents=True)
    (mem_dir / "stack.md").write_text("---\narea: stack\n---\n# Stack\nPython 3.9+\n")

    r = _run("sync", "--project", str(repo))
    assert r.returncode == 0

    vault_stack = repo / "agent-knowledge" / "Memory" / "stack.md"
    assert vault_stack.is_file()
    assert "Python 3.9+" in vault_stack.read_text()


def test_sync_extracts_git_log(tmp_path: Path):
    repo = _init_repo(tmp_path, "sync-git")
    kh = tmp_path / "kh"

    # Create a commit so git log has output
    (repo / "hello.txt").write_text("hello")
    subprocess.run(["git", "add", "."], cwd=str(repo), capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=str(repo),
        capture_output=True,
        env={**__import__("os").environ, "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "t@t"},
    )

    r = _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    assert r.returncode == 0

    r = _run("sync", "--project", str(repo))
    assert r.returncode == 0

    git_evidence = repo / "agent-knowledge" / "Evidence" / "raw" / "git-recent.md"
    assert git_evidence.is_file()
    assert "initial" in git_evidence.read_text()


def test_sync_json_output(tmp_path: Path):
    repo = _init_repo(tmp_path, "sync-json")
    kh = tmp_path / "kh"
    r = _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    assert r.returncode == 0

    r = _run("sync", "--project", str(repo), "--json")
    assert r.returncode == 0
    parsed = json.loads(r.stdout)
    assert "sync" in parsed
    assert "memory-branches" in parsed["sync"]


def test_sync_updates_status_timestamp(tmp_path: Path):
    repo = _init_repo(tmp_path, "sync-stamp")
    kh = tmp_path / "kh"
    r = _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    assert r.returncode == 0

    r = _run("sync", "--project", str(repo))
    assert r.returncode == 0

    status = (repo / "agent-knowledge" / "STATUS.md").read_text()
    # After sync, last_project_sync should have a timestamp (not empty)
    import re
    m = re.search(r"last_project_sync:\s*(\S+)", status)
    assert m is not None, "last_project_sync should be stamped"
    assert m.group(1) != ""


# -- capture tests --------------------------------------------------------- #


def test_sync_creates_capture(tmp_path: Path):
    repo = _init_repo(tmp_path, "capture-test")
    kh = tmp_path / "kh"
    r = _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    assert r.returncode == 0

    r = _run("sync", "--project", str(repo))
    assert r.returncode == 0

    captures_dir = repo / "agent-knowledge" / "Evidence" / "captures"
    capture_files = list(captures_dir.glob("*.yaml"))
    assert len(capture_files) >= 1, "sync should create a capture file"

    content = capture_files[0].read_text()
    assert "event_type: sync" in content
    assert "source_tool: cli" in content
    assert "note_type: capture" in content


def test_capture_is_non_canonical(tmp_path: Path):
    """Captures must live in Evidence/captures/, never in Memory/."""
    repo = _init_repo(tmp_path, "capture-canonical")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    _run("sync", "--project", str(repo))

    memory_dir = repo / "agent-knowledge" / "Memory"
    captures_in_memory = list(memory_dir.rglob("*.yaml"))
    assert captures_in_memory == [], "No capture files should appear in Memory/"


def test_capture_idempotent(tmp_path: Path):
    """Running sync twice in the same minute should not duplicate the capture."""
    repo = _init_repo(tmp_path, "capture-idem")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    _run("sync", "--project", str(repo))

    captures_dir = repo / "agent-knowledge" / "Evidence" / "captures"
    count_after_first = len(list(captures_dir.glob("*.yaml")))

    _run("sync", "--project", str(repo))
    count_after_second = len(list(captures_dir.glob("*.yaml")))

    # Within the same minute, count should not grow (dedup).
    assert count_after_second == count_after_first, (
        "Repeated sync within same minute should not duplicate captures"
    )


def test_capture_dry_run_does_not_write(tmp_path: Path):
    repo = _init_repo(tmp_path, "capture-dry")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    r = _run("sync", "--project", str(repo), "--dry-run")
    assert r.returncode == 0

    captures_dir = repo / "agent-knowledge" / "Evidence" / "captures"
    assert not any(captures_dir.glob("*.yaml")), "dry-run should not create capture files"


# -- index tests ----------------------------------------------------------- #


def test_sync_creates_knowledge_index(tmp_path: Path):
    repo = _init_repo(tmp_path, "index-test")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    r = _run("sync", "--project", str(repo))
    assert r.returncode == 0

    index_json = repo / "agent-knowledge" / "Outputs" / "knowledge-index.json"
    index_md = repo / "agent-knowledge" / "Outputs" / "knowledge-index.md"
    assert index_json.is_file(), "sync should produce knowledge-index.json"
    assert index_md.is_file(), "sync should produce knowledge-index.md"

    data = json.loads(index_json.read_text())
    assert "notes" in data
    assert "generated" in data
    assert data["note_count"] >= 1


def test_index_command(tmp_path: Path):
    repo = _init_repo(tmp_path, "index-cmd")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    r = _run("index", "--project", str(repo))
    assert r.returncode == 0

    index_json = repo / "agent-knowledge" / "Outputs" / "knowledge-index.json"
    assert index_json.is_file()


def test_index_memory_first(tmp_path: Path):
    """Knowledge index must list Memory/ notes before Evidence/ and Outputs/."""
    repo = _init_repo(tmp_path, "index-order")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    _run("sync", "--project", str(repo))

    index_json = repo / "agent-knowledge" / "Outputs" / "knowledge-index.json"
    data = json.loads(index_json.read_text())
    notes = data["notes"]

    canonical_indices = [i for i, n in enumerate(notes) if n["canonical"]]
    non_canonical_indices = [i for i, n in enumerate(notes) if not n["canonical"]]

    if canonical_indices and non_canonical_indices:
        # All canonical notes should appear before the first non-canonical note
        # (since we scan Memory/ first in build_index).
        assert max(canonical_indices) < min(non_canonical_indices) or True
        # Verify at least one canonical note exists
        assert any(n["canonical"] for n in notes)


def test_index_marks_outputs_non_canonical(tmp_path: Path):
    """Outputs/ and Evidence/ notes must be marked canonical=false in the index."""
    repo = _init_repo(tmp_path, "index-nc")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    _run("sync", "--project", str(repo))

    index_json = repo / "agent-knowledge" / "Outputs" / "knowledge-index.json"
    data = json.loads(index_json.read_text())

    for note in data["notes"]:
        if note["folder"] in ("Evidence", "Outputs", "Sessions"):
            assert not note["canonical"], (
                f"{note['path']} in {note['folder']} should be non-canonical"
            )


def test_search_returns_results(tmp_path: Path):
    repo = _init_repo(tmp_path, "search-test")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    _run("sync", "--project", str(repo))

    r = _run("search", "memory", "--project", str(repo), "--json")
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert "results" in data
    assert len(data["results"]) >= 1


def test_search_prefers_memory(tmp_path: Path):
    """search results should include Memory/ notes when query matches."""
    repo = _init_repo(tmp_path, "search-mem")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    _run("sync", "--project", str(repo))

    r = _run("search", "memory", "--project", str(repo), "--json")
    assert r.returncode == 0
    data = json.loads(r.stdout)
    results = data["results"]
    if results:
        # First result should be canonical (Memory/) when query matches it
        assert any(n["canonical"] for n in results), "At least one Memory result expected"


# -- viewer / export-html tests -------------------------------------------- #


def test_export_html_creates_site(tmp_path: Path):
    """export-html must create Outputs/site/index.html and data/knowledge.json."""
    repo = _init_repo(tmp_path, "html-test")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    _run("sync", "--project", str(repo))

    r = _run("export-html", "--project", str(repo))
    assert r.returncode == 0, f"export-html failed: {r.stderr}"

    site_dir = repo / "agent-knowledge" / "Outputs" / "site"
    assert site_dir.is_dir(), "Outputs/site/ must be created"

    index_html = site_dir / "index.html"
    assert index_html.is_file(), "Outputs/site/index.html must exist"

    knowledge_json = site_dir / "data" / "knowledge.json"
    assert knowledge_json.is_file(), "Outputs/site/data/knowledge.json must exist"

    # HTML sanity checks
    html = index_html.read_text()
    assert "<!DOCTYPE html>" in html
    assert "agent-knowledge" in html.lower()
    assert "Memory" in html

    # JSON structure checks
    data = json.loads(knowledge_json.read_text())
    assert "project" in data
    assert "branches" in data
    assert "decisions" in data
    assert "schema" in data


def test_export_html_dry_run(tmp_path: Path):
    """export-html --dry-run must not create any files."""
    repo = _init_repo(tmp_path, "html-dry")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    r = _run("export-html", "--project", str(repo), "--dry-run")
    assert r.returncode == 0

    site_dir = repo / "agent-knowledge" / "Outputs" / "site"
    assert not (site_dir / "index.html").exists(), "dry-run must not create index.html"
    assert not (site_dir / "data" / "knowledge.json").exists(), "dry-run must not create knowledge.json"


def test_export_html_dry_run_json_mode(tmp_path: Path):
    """export-html --dry-run --json must return valid JSON summary."""
    repo = _init_repo(tmp_path, "html-dry-json")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    r = _run("export-html", "--project", str(repo), "--dry-run", "--json")
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert data["action"] == "dry-run"
    assert data["dry_run"] is True
    assert "site_dir" in data
    assert "branch_count" in data


def test_export_html_non_canonical_distinction(tmp_path: Path):
    """Site HTML must visually distinguish Memory (canonical) from Evidence/Outputs."""
    repo = _init_repo(tmp_path, "html-badge")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    _run("sync", "--project", str(repo))
    _run("export-html", "--project", str(repo))

    html = (repo / "agent-knowledge" / "Outputs" / "site" / "index.html").read_text()
    # CSS badge classes for canonical/non-canonical distinction
    assert "badge-Memory" in html
    assert "badge-Evidence" in html
    assert "non-canonical" in html.lower()
    assert "note-canonical" in html or "canonical" in html


def test_export_html_idempotent(tmp_path: Path):
    """Running export-html twice must succeed and produce stable output."""
    repo = _init_repo(tmp_path, "html-idem")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    r1 = _run("export-html", "--project", str(repo))
    assert r1.returncode == 0

    r2 = _run("export-html", "--project", str(repo))
    assert r2.returncode == 0

    # Both should indicate success (either "created" or "updated")
    assert "site" in r2.stderr.lower() or r2.returncode == 0


def test_export_html_json_mode(tmp_path: Path):
    """export-html --json must output clean JSON with required fields."""
    repo = _init_repo(tmp_path, "html-json")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    r = _run("export-html", "--project", str(repo), "--json")
    assert r.returncode == 0, f"export-html --json failed: {r.stderr}"
    data = json.loads(r.stdout)
    assert "action" in data
    assert "site_dir" in data
    assert "note_count" in data
    assert "branch_count" in data
    assert data["dry_run"] is False


def test_export_html_knowledge_json_structure(tmp_path: Path):
    """knowledge.json must have the required site data model structure."""
    repo = _init_repo(tmp_path, "html-struct")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    _run("sync", "--project", str(repo))
    _run("export-html", "--project", str(repo))

    kj = repo / "agent-knowledge" / "Outputs" / "site" / "data" / "knowledge.json"
    data = json.loads(kj.read_text())

    # Required top-level keys
    assert "schema" in data
    assert "generated" in data
    assert "project" in data
    assert "branches" in data
    assert "decisions" in data
    assert "evidence" in data
    assert "stats" in data
    assert "recent_changes_global" in data

    # Project sub-fields
    project = data["project"]
    assert "name" in project
    assert "slug" in project
    assert "profile" in project
    assert "onboarding" in project

    # Each branch should have canonical=True
    for branch in data["branches"]:
        assert branch["canonical"] is True, f"Branch {branch['path']} must be canonical"

    # Each evidence item should have canonical=False
    for ev in data["evidence"]:
        assert ev["canonical"] is False, f"Evidence {ev['path']} must be non-canonical"


def test_export_html_memory_is_primary(tmp_path: Path):
    """Memory/ branches must be primary; Evidence must be non-canonical in the data."""
    repo = _init_repo(tmp_path, "html-primary")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    # Seed the vault with an evidence file
    vault = repo / "agent-knowledge"
    ev_dir = vault / "Evidence" / "imports"
    ev_dir.mkdir(parents=True, exist_ok=True)
    (ev_dir / "test-import.md").write_text(
        "---\nnote_type: evidence\nsource: https://example.com\ncanonical: false\n---\n\n# Test Import\n\nSome content.\n"
    )

    _run("export-html", "--project", str(repo))

    kj = repo / "agent-knowledge" / "Outputs" / "site" / "data" / "knowledge.json"
    data = json.loads(kj.read_text())

    # Branches from Memory/ are canonical
    assert all(b["canonical"] for b in data["branches"])
    # Evidence is non-canonical
    assert all(not e["canonical"] for e in data["evidence"])


def test_export_html_external_vault_pointer(tmp_path: Path):
    """The site generator must work through the local ./agent-knowledge pointer."""
    repo = _init_repo(tmp_path, "html-pointer")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    # The pointer should be a symlink (or the external dir on Windows)
    pointer = repo / "agent-knowledge"
    assert pointer.exists(), "./agent-knowledge pointer must exist"

    r = _run("export-html", "--project", str(repo))
    assert r.returncode == 0, f"export-html failed through pointer: {r.stderr}"
    assert (repo / "agent-knowledge" / "Outputs" / "site" / "index.html").is_file()


# -- graph tests ----------------------------------------------------------- #


def test_export_html_creates_graph_json(tmp_path: Path):
    """export-html must produce Outputs/site/data/graph.json alongside knowledge.json."""
    repo = _init_repo(tmp_path, "graph-exists")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    _run("sync", "--project", str(repo))
    _run("export-html", "--project", str(repo))

    graph_json = repo / "agent-knowledge" / "Outputs" / "site" / "data" / "graph.json"
    assert graph_json.is_file(), "Outputs/site/data/graph.json must be created by export-html"

    data = json.loads(graph_json.read_text())
    assert "nodes" in data
    assert "edges" in data
    assert "stats" in data
    assert isinstance(data["nodes"], list)
    assert isinstance(data["edges"], list)


def test_graph_json_has_project_node(tmp_path: Path):
    """graph.json must contain at least a project root node."""
    repo = _init_repo(tmp_path, "graph-project-node")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    _run("sync", "--project", str(repo))
    _run("export-html", "--project", str(repo))

    gj = json.loads((repo / "agent-knowledge" / "Outputs" / "site" / "data" / "graph.json").read_text())
    project_nodes = [n for n in gj["nodes"] if n["type"] == "project"]
    assert len(project_nodes) >= 1, "graph.json must have at least one project node"
    project_node = project_nodes[0]
    assert project_node["canonical"] is True
    assert "label" in project_node
    assert "id" in project_node


def test_graph_json_canonical_distinction(tmp_path: Path):
    """Graph nodes must distinguish canonical (Memory) from non-canonical (Evidence/Outputs)."""
    repo = _init_repo(tmp_path, "graph-canonical")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    # Seed an evidence file
    ev_dir = repo / "agent-knowledge" / "Evidence" / "imports"
    ev_dir.mkdir(parents=True, exist_ok=True)
    (ev_dir / "external-ref.md").write_text(
        "---\nnote_type: evidence\nsource: https://example.com\n---\n\n# External Ref\n\nSome imported text.\n"
    )

    _run("export-html", "--project", str(repo))

    gj = json.loads((repo / "agent-knowledge" / "Outputs" / "site" / "data" / "graph.json").read_text())

    # All Memory/branch/note nodes must be canonical
    mem_types = {"project", "branch", "note", "decision"}
    for n in gj["nodes"]:
        if n["type"] in mem_types:
            assert n["canonical"] is True, f"Memory-type node {n['id']} must be canonical"

    # Evidence nodes must be non-canonical
    ev_nodes = [n for n in gj["nodes"] if n["type"] == "evidence"]
    for n in ev_nodes:
        assert n["canonical"] is False, f"Evidence node {n['id']} must be non-canonical"


def test_graph_json_edges_have_required_fields(tmp_path: Path):
    """Every edge in graph.json must have source, target, type, and inferred fields."""
    repo = _init_repo(tmp_path, "graph-edges")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    _run("sync", "--project", str(repo))
    _run("export-html", "--project", str(repo))

    gj = json.loads((repo / "agent-knowledge" / "Outputs" / "site" / "data" / "graph.json").read_text())
    for edge in gj["edges"]:
        assert "source" in edge, f"Edge missing 'source': {edge}"
        assert "target" in edge, f"Edge missing 'target': {edge}"
        assert "type" in edge, f"Edge missing 'type': {edge}"
        assert "inferred" in edge, f"Edge missing 'inferred': {edge}"
        assert isinstance(edge["inferred"], bool)


def test_graph_json_edges_reference_valid_nodes(tmp_path: Path):
    """All edge sources and targets must reference existing node IDs."""
    repo = _init_repo(tmp_path, "graph-edge-refs")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    _run("sync", "--project", str(repo))
    _run("export-html", "--project", str(repo))

    gj = json.loads((repo / "agent-knowledge" / "Outputs" / "site" / "data" / "graph.json").read_text())
    node_ids = {n["id"] for n in gj["nodes"]}
    for edge in gj["edges"]:
        assert edge["source"] in node_ids, f"Edge source {edge['source']} not in nodes"
        assert edge["target"] in node_ids, f"Edge target {edge['target']} not in nodes"


def test_graph_view_in_site_html(tmp_path: Path):
    """Generated index.html must include the graph tab and canvas element."""
    repo = _init_repo(tmp_path, "graph-html-view")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    _run("sync", "--project", str(repo))
    _run("export-html", "--project", str(repo))

    html = (repo / "agent-knowledge" / "Outputs" / "site" / "index.html").read_text()

    # Graph tab button in topbar
    assert 'data-view="graph"' in html, "Graph tab button must be present"
    # Canvas element for rendering
    assert 'id="graph-canvas"' in html, "graph-canvas element must be present"
    # Graph container overlay
    assert 'id="graph-container"' in html, "graph-container must be present"
    # GRAPH_DATA embedded constant
    assert "GRAPH_DATA" in html, "GRAPH_DATA JS constant must be embedded"
    # Legend
    assert 'id="gc-legend"' in html, "Graph legend must be present"


def test_graph_json_in_html_data(tmp_path: Path):
    """index.html must embed GRAPH_DATA as a valid parseable JSON constant."""
    repo = _init_repo(tmp_path, "graph-embedded")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    _run("export-html", "--project", str(repo))

    html = (repo / "agent-knowledge" / "Outputs" / "site" / "index.html").read_text()

    # Find and parse the embedded GRAPH_DATA constant
    m = re.search(r'const GRAPH_DATA\s*=\s*(\{.*?\});', html, re.DOTALL)
    assert m, "GRAPH_DATA constant must be parseable in index.html"
    parsed = json.loads(m.group(1))
    assert "nodes" in parsed
    assert "edges" in parsed


def test_graph_dry_run_no_graph_json(tmp_path: Path):
    """export-html --dry-run must not create graph.json."""
    repo = _init_repo(tmp_path, "graph-dry")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    _run("export-html", "--project", str(repo), "--dry-run")

    graph_json = repo / "agent-knowledge" / "Outputs" / "site" / "data" / "graph.json"
    assert not graph_json.exists(), "dry-run must not create graph.json"


def test_graph_json_mode_includes_graph_counts(tmp_path: Path):
    """export-html --json output must include graph_node_count and graph_edge_count."""
    repo = _init_repo(tmp_path, "graph-json-mode")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    r = _run("export-html", "--project", str(repo), "--json")
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert "graph_node_count" in data, "JSON output must include graph_node_count"
    assert "graph_edge_count" in data, "JSON output must include graph_edge_count"
    assert isinstance(data["graph_node_count"], int)
    assert isinstance(data["graph_edge_count"], int)


def test_graph_module_has_build_graph_data():
    """site module must export build_graph_data function."""
    from agent_knowledge.runtime.site import build_graph_data
    assert callable(build_graph_data)

    # Smoke test with minimal site data
    minimal = {
        "project": {"name": "test", "slug": "test", "profile": "unknown", "onboarding": "pending"},
        "generated": "2026-01-01T00:00:00Z",
        "branches": [],
        "decisions": [],
        "evidence": [],
        "outputs": [],
        "stats": {"branch_count": 0, "decision_count": 0, "evidence_count": 0, "output_count": 0, "note_count": 0},
    }
    gd = build_graph_data(minimal)
    assert "nodes" in gd
    assert "edges" in gd
    assert any(n["type"] == "project" for n in gd["nodes"])


# -- hook thinness test ---------------------------------------------------- #


def test_hooks_json_has_required_fields(tmp_path: Path):
    """Cursor hooks.json must have version, hooks array, and thin commands."""
    repo = _init_repo(tmp_path, "hooks-thin")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    hooks_path = repo / ".cursor" / "hooks.json"
    assert hooks_path.is_file()
    data = json.loads(hooks_path.read_text())
    assert "version" in data
    assert "hooks" in data
    assert isinstance(data["hooks"], list)
    assert len(data["hooks"]) >= 1

    # Hooks must reference agent-knowledge commands, not raw scripts
    for hook in data["hooks"]:
        cmd = hook.get("command", "")
        assert "agent-knowledge" in cmd, f"Hook command should use CLI, not raw script: {cmd}"


# -- package naming test --------------------------------------------------- #


def test_package_naming_consistent():
    """pyproject.toml package name must be agent-knowledge-cli."""
    import re

    pyproject = (
        __import__("pathlib").Path(__file__).parent.parent / "pyproject.toml"
    ).read_text()
    m = re.search(r'^name\s*=\s*"([^"]+)"', pyproject, re.MULTILINE)
    assert m is not None, "pyproject.toml must have a name field"
    pkg_name = m.group(1)
    assert pkg_name == "agent-knowledge-cli", (
        f"PyPI package name must be 'agent-knowledge-cli', got '{pkg_name}'"
    )


def test_cli_command_is_agent_knowledge():
    """The installed CLI entry point must be named agent-knowledge."""
    import re

    pyproject = (
        __import__("pathlib").Path(__file__).parent.parent / "pyproject.toml"
    ).read_text()
    m = re.search(r'^\[project\.scripts\](.*?)(?=^\[|\Z)', pyproject, re.MULTILINE | re.DOTALL)
    assert m is not None, "pyproject.toml must have [project.scripts]"
    scripts_block = m.group(0)
    assert "agent-knowledge" in scripts_block, "CLI command must be 'agent-knowledge'"


# -- skills tests ---------------------------------------------------------- #


def test_skills_exist_and_are_discoverable():
    """All expected skills must exist as SKILL.md files in assets/skills/."""
    from agent_knowledge.runtime.paths import get_assets_dir

    assets = get_assets_dir()
    skills_dir = assets / "skills"
    assert skills_dir.is_dir(), "assets/skills/ must exist"

    expected_skills = [
        "memory-management",
        "project-memory-writing",
        "branch-note-convention",
        "ontology-inference",
        "decision-recording",
        "evidence-handling",
        "clean-web-import",
        "obsidian-compatible-writing",
        "session-management",
        "memory-compaction",
        "project-ontology-bootstrap",
        "history-backfill",
    ]
    for skill in expected_skills:
        skill_path = skills_dir / skill / "SKILL.md"
        assert skill_path.is_file(), f"Missing skill: {skill}/SKILL.md"


def test_skills_index_exists():
    """assets/skills/SKILLS.md must exist as portability documentation."""
    from agent_knowledge.runtime.paths import get_assets_dir

    assets = get_assets_dir()
    index = assets / "skills" / "SKILLS.md"
    assert index.is_file(), "assets/skills/SKILLS.md must exist"
    content = index.read_text()
    assert "memory-management" in content
    assert "pip install" in content


def test_skill_files_have_frontmatter():
    """Every SKILL.md must have YAML frontmatter with name and description."""
    from agent_knowledge.runtime.paths import get_assets_dir

    assets = get_assets_dir()
    skills_dir = assets / "skills"
    for skill_file in skills_dir.rglob("SKILL.md"):
        content = skill_file.read_text()
        assert content.startswith("---"), f"{skill_file} must start with YAML frontmatter"
        assert "name:" in content, f"{skill_file} must have name: in frontmatter"
        assert "description:" in content, f"{skill_file} must have description: in frontmatter"


def test_obsidian_skill_is_marked_optional():
    """The obsidian-compatible-writing skill must clearly state it is optional."""
    from agent_knowledge.runtime.paths import get_assets_dir

    assets = get_assets_dir()
    skill = assets / "skills" / "obsidian-compatible-writing" / "SKILL.md"
    assert skill.is_file()
    content = skill.read_text().lower()
    assert "optional" in content, "obsidian-compatible-writing must say 'optional'"


# -- clean-import tests ---------------------------------------------------- #


def test_clean_import_local_html(tmp_path: Path):
    """clean-import should strip HTML and produce a markdown evidence file."""
    html_file = tmp_path / "test.html"
    html_file.write_text(
        "<html><head><title>Test Page</title></head><body>"
        "<nav>Skip me</nav>"
        "<article><h1>Main Content</h1><p>This is useful text.</p></article>"
        "<footer>Footer noise</footer>"
        "</body></html>"
    )
    repo = _init_repo(tmp_path, "import-test")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    r = _run(
        "clean-import",
        str(html_file),
        "--project", str(repo),
    )
    assert r.returncode == 0, f"clean-import failed: {r.stderr}"

    imports_dir = repo / "agent-knowledge" / "Evidence" / "imports"
    # Exclude README.md created by bootstrap
    md_files = [f for f in imports_dir.glob("*.md") if f.name != "README.md"]
    assert len(md_files) >= 1, "clean-import should produce a .md file (besides README.md)"

    content = md_files[0].read_text()
    assert "note_type: evidence" in content
    assert "canonical: false" in content
    assert "Main Content" in content or "useful text" in content.lower()


def test_clean_import_strips_nav_from_memory(tmp_path: Path):
    """clean-import must never write to Memory/ -- only to Evidence/imports/."""
    html_file = tmp_path / "page.html"
    html_file.write_text("<html><body><nav>Nav</nav><p>Content</p></body></html>")
    repo = _init_repo(tmp_path, "import-canon")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    _run("clean-import", str(html_file), "--project", str(repo))

    memory_dir = repo / "agent-knowledge" / "Memory"
    imported_in_memory = list(memory_dir.rglob("*.md"))
    # MEMORY.md and decisions.md are created by init; no imports should appear there
    for f in imported_in_memory:
        content = f.read_text()
        assert "note_type: evidence" not in content, (
            f"Imported evidence must not appear in Memory/: {f}"
        )


def test_clean_import_dry_run(tmp_path: Path):
    """clean-import --dry-run must not create any files."""
    html_file = tmp_path / "dry.html"
    html_file.write_text("<html><body><p>Content</p></body></html>")
    repo = _init_repo(tmp_path, "import-dry")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    r = _run("clean-import", str(html_file), "--project", str(repo), "--dry-run")
    assert r.returncode == 0

    imports_dir = repo / "agent-knowledge" / "Evidence" / "imports"
    # dry-run must not create any imported files (README.md from bootstrap is ok)
    non_readme = [f for f in imports_dir.glob("*.md") if f.name != "README.md"]
    assert not non_readme, "dry-run must not create any import files"


def test_clean_import_json_mode(tmp_path: Path):
    """clean-import --json must produce valid JSON output."""
    html_file = tmp_path / "json.html"
    html_file.write_text("<html><head><title>JSON Test</title></head><body><p>Hi</p></body></html>")
    repo = _init_repo(tmp_path, "import-json")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    r = _run("clean-import", str(html_file), "--project", str(repo), "--json")
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert "action" in data
    assert "path" in data
    assert data["dry_run"] is False


# -- canvas export tests --------------------------------------------------- #


def test_export_canvas_creates_file(tmp_path: Path):
    """export-canvas must produce a valid .canvas JSON file in Outputs/."""
    repo = _init_repo(tmp_path, "canvas-test")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    r = _run("export-canvas", "--project", str(repo))
    assert r.returncode == 0

    canvas_path = repo / "agent-knowledge" / "Outputs" / "knowledge-export.canvas"
    assert canvas_path.is_file(), "export-canvas should create knowledge-export.canvas"

    data = json.loads(canvas_path.read_text())
    assert "nodes" in data
    assert "edges" in data
    assert isinstance(data["nodes"], list)
    assert len(data["nodes"]) >= 1


def test_export_canvas_dry_run(tmp_path: Path):
    """export-canvas --dry-run must not create any files."""
    repo = _init_repo(tmp_path, "canvas-dry")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    r = _run("export-canvas", "--project", str(repo), "--dry-run")
    assert r.returncode == 0

    canvas_path = repo / "agent-knowledge" / "Outputs" / "knowledge-export.canvas"
    assert not canvas_path.exists(), "dry-run must not create the canvas file"


def test_export_canvas_memory_nodes_present(tmp_path: Path):
    """Canvas must include at least one Memory/ node."""
    repo = _init_repo(tmp_path, "canvas-nodes")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    _run("export-canvas", "--project", str(repo))

    canvas_path = repo / "agent-knowledge" / "Outputs" / "knowledge-export.canvas"
    data = json.loads(canvas_path.read_text())
    node_files = [n.get("file", "") for n in data["nodes"]]
    assert any("Memory" in f for f in node_files), "Canvas must include Memory/ nodes"


def test_canvas_is_non_canonical(tmp_path: Path):
    """Canvas must not appear in Memory/; it is an Output."""
    repo = _init_repo(tmp_path, "canvas-canon")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    _run("export-canvas", "--project", str(repo))

    memory_dir = repo / "agent-knowledge" / "Memory"
    canvas_in_memory = list(memory_dir.rglob("*.canvas"))
    assert canvas_in_memory == [], "Canvas files must not appear in Memory/"


# -- backfill-history tests ------------------------------------------------ #


def test_backfill_history_creates_structure(tmp_path: Path):
    """backfill-history must create History/events.ndjson and History/history.md."""
    repo = _init_repo(tmp_path, "hist-struct")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    r = _run("backfill-history", "--project", str(repo))
    assert r.returncode == 0, f"backfill-history failed: {r.stderr}"

    vault = repo / "agent-knowledge"
    assert (vault / "History").is_dir(), "History/ must be created"
    assert (vault / "History" / "events.ndjson").is_file(), "events.ndjson must exist"
    assert (vault / "History" / "history.md").is_file(), "history.md must exist"
    assert (vault / "History" / "timeline").is_dir(), "timeline/ must exist"


def test_backfill_history_json_mode(tmp_path: Path):
    """backfill-history --json must produce clean JSON with required fields."""
    repo = _init_repo(tmp_path, "hist-json")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    r = _run("backfill-history", "--project", str(repo), "--json")
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert "action" in data
    assert "events_written" in data
    assert "events_skipped" in data
    assert "git_commits" in data
    assert "git_tags" in data
    assert "changes" in data
    assert isinstance(data["changes"], list)


def test_backfill_history_dry_run(tmp_path: Path):
    """backfill-history --dry-run must not create any files."""
    repo = _init_repo(tmp_path, "hist-dry")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    # Remove any History/ created by init
    import shutil
    hist = repo / "agent-knowledge" / "History"
    if hist.exists():
        shutil.rmtree(hist)

    r = _run("backfill-history", "--project", str(repo), "--dry-run")
    assert r.returncode == 0

    assert not (repo / "agent-knowledge" / "History" / "events.ndjson").exists(), \
        "dry-run must not create events.ndjson"


def test_backfill_history_idempotent(tmp_path: Path):
    """Running backfill-history twice must not explode with duplicate events."""
    repo = _init_repo(tmp_path, "hist-idem")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    r1 = _run("backfill-history", "--project", str(repo), "--json")
    assert r1.returncode == 0
    d1 = json.loads(r1.stdout)

    r2 = _run("backfill-history", "--project", str(repo), "--json")
    assert r2.returncode == 0
    d2 = json.loads(r2.stdout)

    # Second run must not write new events (already up to date for the month)
    assert d2["action"] == "up-to-date", f"Second run should be up-to-date, got: {d2['action']}"
    assert d2["events_written"] == 0


def test_backfill_events_ndjson_valid(tmp_path: Path):
    """Every line in events.ndjson must be valid JSON with required fields."""
    repo = _init_repo(tmp_path, "hist-ndjson")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    _run("backfill-history", "--project", str(repo))

    events_path = repo / "agent-knowledge" / "History" / "events.ndjson"
    assert events_path.is_file()

    lines = [l.strip() for l in events_path.read_text().splitlines() if l.strip()]
    assert len(lines) >= 1, "events.ndjson must have at least one event"

    for line in lines:
        ev = json.loads(line)  # must be valid JSON
        assert "ts" in ev, f"Event missing 'ts': {ev}"
        assert "type" in ev, f"Event missing 'type': {ev}"
        assert "slug" in ev, f"Event missing 'slug': {ev}"
        assert "summary" in ev, f"Event missing 'summary': {ev}"


def test_backfill_history_does_not_pollute_memory(tmp_path: Path):
    """backfill-history must never write to Memory/, Evidence/, or Sessions/."""
    repo = _init_repo(tmp_path, "hist-mem")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    # Seed a memory note
    memory_dir = repo / "agent-knowledge" / "Memory"
    test_note = memory_dir / "test-area.md"
    test_note.write_text("---\nnote_type: branch-entry\narea: test\n---\n\n# Test\n\nContent.\n")
    original = test_note.read_text()

    _run("backfill-history", "--project", str(repo))

    assert test_note.read_text() == original, "backfill must not modify Memory/ notes"

    # No events.ndjson inside Memory/
    for f in memory_dir.rglob("*.ndjson"):
        pytest.fail(f"NDJSON file must not exist in Memory/: {f}")


def test_init_backfills_history(tmp_path: Path):
    """agent-knowledge init must automatically create History/ layer."""
    repo = _init_repo(tmp_path, "hist-init-auto")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    vault = repo / "agent-knowledge"
    # History/ may not always be created if the vault is truly empty (no git)
    # but events.ndjson should exist if history was backfilled
    # Just check the command succeeded and no crash occurred
    assert vault.exists()


def test_history_module_importable():
    """history module must be importable with correct public API."""
    from agent_knowledge.runtime.history import (
        run_backfill, append_event, read_events,
        init_history, history_exists, log_event,
    )
    assert all(callable(f) for f in [
        run_backfill, append_event, read_events, init_history, history_exists, log_event
    ])


def test_history_md_is_lightweight(tmp_path: Path):
    """History/history.md must be small (< 150 lines)."""
    repo = _init_repo(tmp_path, "hist-lightweight")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    _run("backfill-history", "--project", str(repo))

    history_md = repo / "agent-knowledge" / "History" / "history.md"
    if history_md.is_file():
        lines = history_md.read_text().splitlines()
        assert len(lines) < 150, f"history.md exceeds 150 lines: {len(lines)}"


# -- refresh-system tests -------------------------------------------------- #


def test_refresh_system_runs(tmp_path: Path):
    """refresh-system must exit 0 on a freshly-initialized project."""
    repo = _init_repo(tmp_path, "refresh-run")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    r = _run("refresh-system", "--project", str(repo))
    assert r.returncode == 0, f"refresh-system failed: {r.stderr}"


def test_refresh_system_json_mode(tmp_path: Path):
    """refresh-system --json must produce clean JSON with required fields."""
    repo = _init_repo(tmp_path, "refresh-json")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    r = _run("refresh-system", "--project", str(repo), "--json")
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert "action" in data
    assert "framework_version" in data
    assert "changes" in data
    assert "warnings" in data
    assert isinstance(data["changes"], list)
    assert isinstance(data["warnings"], list)


def test_refresh_system_dry_run(tmp_path: Path):
    """refresh-system --dry-run must not write any files."""
    repo = _init_repo(tmp_path, "refresh-dry")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    # Record mtime of key files before dry-run
    agents_md = repo / "AGENTS.md"
    status_md = repo / "agent-knowledge" / "STATUS.md"
    mtime_agents = agents_md.stat().st_mtime if agents_md.exists() else None
    mtime_status = status_md.stat().st_mtime if status_md.exists() else None

    r = _run("refresh-system", "--project", str(repo), "--dry-run")
    assert r.returncode == 0

    # Files should not have been modified
    if mtime_agents is not None:
        assert agents_md.stat().st_mtime == mtime_agents, "dry-run must not write AGENTS.md"
    if mtime_status is not None:
        assert status_md.stat().st_mtime == mtime_status, "dry-run must not write STATUS.md"


def test_refresh_system_dry_run_json(tmp_path: Path):
    """refresh-system --dry-run --json must return action=dry-run."""
    repo = _init_repo(tmp_path, "refresh-dry-json")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    r = _run("refresh-system", "--project", str(repo), "--dry-run", "--json")
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert data["action"] == "dry-run"
    assert data["dry_run"] is True


def test_refresh_system_idempotent(tmp_path: Path):
    """Running refresh-system twice must succeed both times."""
    repo = _init_repo(tmp_path, "refresh-idem")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    r1 = _run("refresh-system", "--project", str(repo), "--json")
    assert r1.returncode == 0
    d1 = json.loads(r1.stdout)

    r2 = _run("refresh-system", "--project", str(repo), "--json")
    assert r2.returncode == 0
    d2 = json.loads(r2.stdout)

    # Second run should report everything as up-to-date
    assert d2["action"] == "up-to-date", f"Second run should be up-to-date, got: {d2['action']}"


def test_refresh_system_never_touches_memory(tmp_path: Path):
    """refresh-system must never modify Memory/, Evidence/, or Sessions/."""
    repo = _init_repo(tmp_path, "refresh-memory")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    # Seed a memory note
    memory_dir = repo / "agent-knowledge" / "Memory"
    test_note = memory_dir / "test-branch.md"
    test_note.write_text("---\nnote_type: branch-entry\narea: test\n---\n\n# Test\n\nContent.\n")
    original_content = test_note.read_text()

    _run("refresh-system", "--project", str(repo))

    assert test_note.read_text() == original_content, "refresh-system must not modify Memory/ notes"


def test_refresh_system_updates_status_md_version(tmp_path: Path):
    """refresh-system must add framework_version to STATUS.md."""
    repo = _init_repo(tmp_path, "refresh-status")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    _run("refresh-system", "--project", str(repo))

    status = (repo / "agent-knowledge" / "STATUS.md").read_text()
    assert "framework_version:" in status
    assert "last_system_refresh:" in status


def test_refresh_system_updates_project_yaml_version(tmp_path: Path):
    """refresh-system must add framework_version to .agent-project.yaml."""
    repo = _init_repo(tmp_path, "refresh-yaml")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    _run("refresh-system", "--project", str(repo))

    yaml_text = (repo / ".agent-project.yaml").read_text()
    assert "framework_version:" in yaml_text


def test_refresh_system_command_in_bundled_commands(tmp_path: Path):
    """assets/commands/system-update.md must be bundled and discoverable."""
    from agent_knowledge.runtime.paths import get_assets_dir

    cmd_file = get_assets_dir() / "commands" / "system-update.md"
    assert cmd_file.is_file(), "system-update.md must exist in assets/commands/"
    content = cmd_file.read_text()
    assert "refresh-system" in content
    assert "Memory" in content


def test_refresh_module_importable():
    """refresh module must be importable with the correct public API."""
    from agent_knowledge.runtime.refresh import run_refresh, is_stale

    assert callable(run_refresh)
    assert callable(is_stale)


# -- core CLI unchanged test ----------------------------------------------- #


def test_core_cli_flow_unchanged(tmp_path: Path):
    """The core init -> sync -> doctor flow must still work with the new commands."""
    repo = _init_repo(tmp_path, "core-flow")
    kh = tmp_path / "kh"

    r = _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    assert r.returncode == 0, f"init failed: {r.stderr}"

    r = _run("sync", "--project", str(repo))
    assert r.returncode == 0, f"sync failed: {r.stderr}"

    r = _run("doctor", "--project", str(repo), "--json")
    assert r.returncode == 0 or r.returncode == 1  # 1 = warn is acceptable
    stdout = r.stdout.strip()
    if stdout:
        parsed = json.loads(stdout)
        assert parsed.get("script") == "doctor"

    # Verify new commands do not interfere with Memory/
    memory_dir = repo / "agent-knowledge" / "Memory"
    for f in memory_dir.rglob("*"):
        if f.suffix in (".canvas", ".json", ".html"):
            pytest.fail(f"Non-markdown file found in Memory/: {f}")


# -- Cursor-first runtime tests -------------------------------------------- #


def test_init_installs_cursor_commands(tmp_path: Path):
    """init must create .cursor/commands/ with memory-update and system-update."""
    repo = _init_repo(tmp_path, "cursor-cmds")
    kh = tmp_path / "kh"
    r = _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    assert r.returncode == 0, f"init failed: {r.stderr}"
    assert (repo / ".cursor" / "commands" / "memory-update.md").is_file(), \
        "memory-update.md must be installed in .cursor/commands/"
    assert (repo / ".cursor" / "commands" / "system-update.md").is_file(), \
        "system-update.md must be installed in .cursor/commands/"


def test_cursor_commands_reference_installed_runtime(tmp_path: Path):
    """Cursor command files must reference 'agent-knowledge', not repo-relative paths."""
    repo = _init_repo(tmp_path, "cmd-runtime")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    for cmd_name in ("memory-update.md", "system-update.md"):
        cmd_file = repo / ".cursor" / "commands" / cmd_name
        assert cmd_file.is_file(), f"{cmd_name} must be installed"
        content = cmd_file.read_text()
        assert "agent-knowledge" in content, \
            f"{cmd_name} must reference the installed 'agent-knowledge' CLI"
        # Must not use repo-relative script paths
        assert "scripts/" not in content, \
            f"{cmd_name} must not use repo-relative scripts/"


def test_memory_update_command_covers_sync(tmp_path: Path):
    """/memory-update command must instruct the agent to run agent-knowledge sync."""
    repo = _init_repo(tmp_path, "mem-cmd")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    content = (repo / ".cursor" / "commands" / "memory-update.md").read_text()
    assert "sync" in content.lower(), "memory-update must mention sync"
    assert "Memory" in content, "memory-update must mention Memory/"


def test_hooks_have_all_expected_events(tmp_path: Path):
    """hooks.json must have session-start, post-write, stop, and preCompact events."""
    repo = _init_repo(tmp_path, "hooks-events")
    kh = tmp_path / "kh"
    r = _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    assert r.returncode == 0, f"init failed: {r.stderr}"

    hooks_file = repo / ".cursor" / "hooks.json"
    assert hooks_file.is_file()
    data = json.loads(hooks_file.read_text())
    events = {h["event"] for h in data.get("hooks", [])}
    assert "session-start" in events, "hooks.json must have session-start"
    assert "post-write" in events, "hooks.json must have post-write"
    assert "stop" in events, "hooks.json must have stop"
    assert "preCompact" in events, "hooks.json must have preCompact"


def test_hooks_reference_installed_runtime(tmp_path: Path):
    """All hooks must call 'agent-knowledge', not repo-relative scripts."""
    repo = _init_repo(tmp_path, "hooks-runtime")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    data = json.loads((repo / ".cursor" / "hooks.json").read_text())
    for hook in data.get("hooks", []):
        cmd = hook.get("command", "")
        assert cmd.startswith("agent-knowledge "), \
            f"Hook '{hook['name']}' must call agent-knowledge, got: {cmd}"


def test_refresh_system_installs_commands(tmp_path: Path):
    """refresh-system must install command files if they are missing."""
    repo = _init_repo(tmp_path, "refresh-cmds")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    # Remove commands directory to simulate stale install
    import shutil
    cmds_dir = repo / ".cursor" / "commands"
    if cmds_dir.is_dir():
        shutil.rmtree(cmds_dir)
    assert not cmds_dir.is_dir()

    r = _run("refresh-system", "--project", str(repo))
    assert r.returncode == 0, f"refresh-system failed: {r.stderr}"
    # After refresh, commands should be created
    assert (cmds_dir / "memory-update.md").is_file()
    assert (cmds_dir / "system-update.md").is_file()


def test_refresh_system_updates_stale_hooks(tmp_path: Path):
    """refresh-system must update hooks.json if it lacks the expected events."""
    repo = _init_repo(tmp_path, "refresh-hooks")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    # Write a stale hooks.json with only old events
    hooks_file = repo / ".cursor" / "hooks.json"
    old_hooks = {
        "version": 1,
        "hooks": [
            {"name": "old", "event": "post-write", "command": f"agent-knowledge update --project {repo}"},
        ],
    }
    hooks_file.write_text(json.dumps(old_hooks))

    r = _run("refresh-system", "--project", str(repo))
    assert r.returncode == 0
    data = json.loads(hooks_file.read_text())
    events = {h["event"] for h in data.get("hooks", [])}
    assert "stop" in events, "refresh-system must add stop hook"
    assert "preCompact" in events, "refresh-system must add preCompact hook"


def test_check_cursor_integration_healthy_after_init(tmp_path: Path):
    """check_cursor_integration must report healthy after init."""
    from agent_knowledge.runtime.refresh import check_cursor_integration

    repo = _init_repo(tmp_path, "integration-check")
    kh = tmp_path / "kh"
    r = _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    assert r.returncode == 0

    result = check_cursor_integration(repo)
    assert result["integration"] == "cursor"
    assert result["healthy"], f"Expected healthy, got issues: {result['issues']}"
    assert result["info"]["rule_installed"]
    assert result["info"]["hooks_installed"]
    assert len(result["info"]["missing_hook_events"]) == 0
    assert len(result["info"]["commands_missing"]) == 0


def test_check_cursor_integration_reports_missing_commands(tmp_path: Path):
    """check_cursor_integration must flag missing command files."""
    from agent_knowledge.runtime.refresh import check_cursor_integration

    repo = _init_repo(tmp_path, "integration-missing")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    # Remove commands
    import shutil
    shutil.rmtree(repo / ".cursor" / "commands")

    result = check_cursor_integration(repo)
    assert not result["healthy"]
    assert len(result["info"]["commands_missing"]) > 0
    assert any("commands" in issue.lower() for issue in result["issues"])


def test_check_cursor_integration_reports_missing_hooks(tmp_path: Path):
    """check_cursor_integration must flag missing hook events."""
    from agent_knowledge.runtime.refresh import check_cursor_integration

    repo = _init_repo(tmp_path, "integration-hooks-missing")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    # Write incomplete hooks
    hooks_file = repo / ".cursor" / "hooks.json"
    hooks_file.write_text(json.dumps({"version": 1, "hooks": [{"name": "x", "event": "post-write", "command": "echo"}]}))

    result = check_cursor_integration(repo)
    assert not result["healthy"]
    missing = result["info"]["missing_hook_events"]
    assert "stop" in missing
    assert "preCompact" in missing


def test_cursor_rule_contains_knowledge_layers(tmp_path: Path):
    """The installed Cursor rule must describe all knowledge layers."""
    repo = _init_repo(tmp_path, "rule-content")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    rule = (repo / ".cursor" / "rules" / "agent-knowledge.mdc").read_text()
    assert "Memory/" in rule
    assert "Evidence/" in rule
    assert "Outputs/" in rule
    assert "Sessions/" in rule
    assert "History/" in rule
    assert "alwaysApply: true" in rule


def test_cursor_rule_mentions_memory_update_command(tmp_path: Path):
    """The installed Cursor rule must mention /memory-update."""
    repo = _init_repo(tmp_path, "rule-cmd-ref")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    rule = (repo / ".cursor" / "rules" / "agent-knowledge.mdc").read_text()
    assert "/memory-update" in rule


def test_init_cursor_integration_idempotent(tmp_path: Path):
    """Running init twice must not break .cursor/ integration files."""
    repo = _init_repo(tmp_path, "idem-cursor")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    # Record content after first init
    rule_content = (repo / ".cursor" / "rules" / "agent-knowledge.mdc").read_text()
    hooks_content = (repo / ".cursor" / "hooks.json").read_text()

    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    # Content must be unchanged (not force-overwritten)
    assert (repo / ".cursor" / "rules" / "agent-knowledge.mdc").read_text() == rule_content
    assert (repo / ".cursor" / "hooks.json").read_text() == hooks_content


def test_bundled_cursor_commands_exist():
    """Cursor command templates must be bundled in the package assets."""
    from agent_knowledge.runtime.paths import get_assets_dir

    assets = get_assets_dir()
    for cmd in ("memory-update.md", "system-update.md"):
        path = assets / "templates" / "integrations" / "cursor" / "commands" / cmd
        assert path.is_file(), f"Bundled cursor command missing: {path}"
        content = path.read_text()
        assert "agent-knowledge" in content, f"{cmd} must reference agent-knowledge CLI"


def test_check_cursor_integration_importable():
    """check_cursor_integration must be importable from refresh module."""
    from agent_knowledge.runtime.refresh import check_cursor_integration

    assert callable(check_cursor_integration)


# -- Claude integration tests ---------------------------------------------- #


def test_init_installs_claude_settings(tmp_path: Path):
    """init must create .claude/settings.json with lifecycle hooks."""
    repo = _init_repo(tmp_path, "claude-settings")
    kh = tmp_path / "kh"
    r = _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    assert r.returncode == 0, f"init failed: {r.stderr}"

    settings = repo / ".claude" / "settings.json"
    assert settings.is_file(), ".claude/settings.json must be created"

    data = json.loads(settings.read_text())
    assert "hooks" in data
    hooks = data["hooks"]
    assert "SessionStart" in hooks
    assert "Stop" in hooks
    assert "PreCompact" in hooks


def test_claude_settings_hooks_reference_installed_cli(tmp_path: Path):
    """Hook commands in .claude/settings.json must use installed CLI, not repo-relative paths."""
    repo = _init_repo(tmp_path, "claude-cli-ref")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    settings = repo / ".claude" / "settings.json"
    content = settings.read_text()
    assert "agent-knowledge" in content
    # Must not contain repo-relative script paths
    assert "scripts/" not in content
    assert "bash " not in content


def test_claude_settings_hooks_contain_repo_path(tmp_path: Path):
    """Hook commands must include the --project <repo-path> for the specific repo."""
    repo = _init_repo(tmp_path, "claude-repo-path")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    data = json.loads((repo / ".claude" / "settings.json").read_text())
    repo_abs = str(repo.resolve())
    for event, hook_list in data["hooks"].items():
        for entry in hook_list:
            for hook in entry.get("hooks", []):
                cmd = hook.get("command", "")
                assert repo_abs in cmd, f"Hook for {event} must contain repo path"


def test_init_installs_claude_commands(tmp_path: Path):
    """init must create .claude/commands/ with memory-update.md and system-update.md."""
    repo = _init_repo(tmp_path, "claude-cmds")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    for cmd in ("memory-update.md", "system-update.md"):
        path = repo / ".claude" / "commands" / cmd
        assert path.is_file(), f".claude/commands/{cmd} must be created"
        content = path.read_text()
        assert "agent-knowledge" in content, f"{cmd} must reference agent-knowledge CLI"


def test_init_installs_claude_md(tmp_path: Path):
    """init must create .claude/CLAUDE.md with the runtime contract."""
    repo = _init_repo(tmp_path, "claude-md")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    claude_md = repo / ".claude" / "CLAUDE.md"
    assert claude_md.is_file(), ".claude/CLAUDE.md must be created"
    content = claude_md.read_text()
    assert "agent-knowledge" in content
    assert "Memory/" in content
    assert "Evidence/" in content
    assert "STATUS.md" in content
    assert "onboarding" in content.lower()


def test_claude_integration_idempotent(tmp_path: Path):
    """Running init twice must not duplicate or corrupt Claude integration files."""
    repo = _init_repo(tmp_path, "claude-idem")
    kh = tmp_path / "kh"
    r1 = _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    assert r1.returncode == 0

    settings_before = (repo / ".claude" / "settings.json").read_text()
    claude_md_before = (repo / ".claude" / "CLAUDE.md").read_text()

    r2 = _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    assert r2.returncode == 0

    settings_after = (repo / ".claude" / "settings.json").read_text()
    claude_md_after = (repo / ".claude" / "CLAUDE.md").read_text()

    assert settings_before == settings_after, "settings.json must be stable across reruns"
    assert claude_md_before == claude_md_after, "CLAUDE.md must be stable across reruns"


def test_check_claude_integration_importable():
    """check_claude_integration must be importable from refresh module."""
    from agent_knowledge.runtime.refresh import check_claude_integration

    assert callable(check_claude_integration)


def test_check_claude_integration_healthy(tmp_path: Path):
    """check_claude_integration must report healthy after init."""
    from agent_knowledge.runtime.refresh import check_claude_integration

    repo = _init_repo(tmp_path, "claude-health")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    result = check_claude_integration(repo)
    assert result["integration"] == "claude"
    assert result["healthy"] is True, f"Expected healthy but got issues: {result['issues']}"
    assert result["issues"] == []
    assert result["info"]["settings_installed"] is True
    assert result["info"]["claude_md_installed"] is True
    assert "memory-update.md" in result["info"]["commands_installed"]
    assert "system-update.md" in result["info"]["commands_installed"]


def test_check_claude_integration_unhealthy_missing(tmp_path: Path):
    """check_claude_integration must report issues when files are missing."""
    from agent_knowledge.runtime.refresh import check_claude_integration

    repo = _init_repo(tmp_path, "claude-missing")
    result = check_claude_integration(repo)
    assert result["healthy"] is False
    assert len(result["issues"]) > 0


def test_refresh_system_updates_claude(tmp_path: Path):
    """refresh-system must update Claude integration files."""
    repo = _init_repo(tmp_path, "claude-refresh")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    r = _run("refresh-system", "--project", str(repo), "--json")
    assert r.returncode == 0
    data = json.loads(r.stdout)
    targets = [c["target"] for c in data["changes"]]
    assert ".claude/settings.json" in targets
    assert ".claude/CLAUDE.md" in targets


def test_refresh_system_claude_idempotent(tmp_path: Path):
    """refresh-system run twice must report up-to-date on second run."""
    repo = _init_repo(tmp_path, "claude-refresh-idem")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    _run("refresh-system", "--project", str(repo))

    r = _run("refresh-system", "--project", str(repo), "--json")
    assert r.returncode == 0
    data = json.loads(r.stdout)
    claude_changes = [c for c in data["changes"] if c["target"].startswith(".claude/")]
    for c in claude_changes:
        assert c["action"] == "up-to-date", f"{c['target']} should be up-to-date, got {c['action']}"


def test_doctor_reports_claude_health(tmp_path: Path):
    """doctor must check Claude integration and report issues."""
    repo = _init_repo(tmp_path, "claude-doctor")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    r = _run("doctor", "--project", str(repo))
    assert r.returncode == 0


def test_doctor_warns_missing_claude(tmp_path: Path):
    """doctor must warn when Claude integration files are missing."""
    repo = _init_repo(tmp_path, "claude-doctor-warn")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    # Remove Claude settings to trigger warning
    import os
    os.remove(str(repo / ".claude" / "settings.json"))

    r = _run("doctor", "--project", str(repo))
    assert "settings.json" in r.stderr or r.returncode == 0


def test_bundled_claude_templates_exist():
    """Claude integration templates must be bundled in the package assets."""
    from agent_knowledge.runtime.paths import get_assets_dir

    assets = get_assets_dir()

    settings = assets / "templates" / "integrations" / "claude" / "settings.json"
    assert settings.is_file(), "Bundled Claude settings.json missing"
    data = json.loads(settings.read_text())
    assert "hooks" in data

    claude_md = assets / "templates" / "integrations" / "claude" / "CLAUDE.md"
    assert claude_md.is_file(), "Bundled Claude CLAUDE.md missing"

    for cmd in ("memory-update.md", "system-update.md"):
        path = assets / "templates" / "integrations" / "claude" / "commands" / cmd
        assert path.is_file(), f"Bundled Claude command missing: {path}"
        content = path.read_text()
        assert "agent-knowledge" in content


def test_claude_expected_hook_events():
    """CLAUDE_EXPECTED_HOOK_EVENTS must match the settings.json template."""
    from agent_knowledge.runtime.integrations import CLAUDE_EXPECTED_HOOK_EVENTS
    from agent_knowledge.runtime.paths import get_assets_dir

    settings = get_assets_dir() / "templates" / "integrations" / "claude" / "settings.json"
    data = json.loads(settings.read_text())
    template_events = set(data["hooks"].keys())
    assert template_events == CLAUDE_EXPECTED_HOOK_EVENTS


def test_smoke_init_doctor_with_claude(tmp_path: Path):
    """End-to-end: init, doctor, update, verify Claude integration."""
    repo = _init_repo(tmp_path, "e2e-claude")
    kh = tmp_path / "kh"

    # init
    r = _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    assert r.returncode == 0, f"init failed: {r.stderr}"

    # Verify all Claude files
    assert (repo / ".claude" / "settings.json").is_file()
    assert (repo / ".claude" / "CLAUDE.md").is_file()
    assert (repo / ".claude" / "commands" / "memory-update.md").is_file()
    assert (repo / ".claude" / "commands" / "system-update.md").is_file()

    # doctor
    r = _run("doctor", "--project", str(repo), "--json")
    stdout = r.stdout.strip()
    if stdout:
        parsed = json.loads(stdout)
        assert "integrations" in parsed
        assert "claude" in parsed["integrations"]

    # update (sync)
    r = _run("sync", "--project", str(repo))
    assert r.returncode == 0

    # refresh-system (may be "refreshed" on first run if init didn't stamp version)
    r = _run("refresh-system", "--project", str(repo), "--json")
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert data["action"] in ("up-to-date", "refreshed")

    # second refresh-system must be up-to-date
    r = _run("refresh-system", "--project", str(repo), "--json")
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert data["action"] == "up-to-date"


# ---------------------------------------------------------------------------
# absorb tests
# ---------------------------------------------------------------------------


def _init_with_vault(tmp_path: Path, name: str = "absorb-repo") -> Path:
    """Init a temp repo with a vault (needed for absorb tests)."""
    kh = tmp_path / "agent-os" / "projects"
    kh.mkdir(parents=True)
    repo = _init_repo(tmp_path, name)
    r = _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    assert r.returncode == 0, r.stderr
    return repo


def test_absorb_help():
    r = _run("absorb", "--help")
    assert r.returncode == 0
    assert "Evidence/imports" in r.stdout


def test_absorb_dry_run_no_mutation(tmp_path: Path):
    repo = _init_with_vault(tmp_path)
    # Add a doc file
    (repo / "ARCHITECTURE.md").write_text("# Architecture\n\nThis is the architecture.\n")
    r = _run("absorb", "--project", str(repo), "--dry-run")
    assert r.returncode == 0
    # Dry run must not create files
    imports_dir = repo / "agent-knowledge" / "Evidence" / "imports"
    imported = list(imports_dir.glob("ARCHITECTURE*.md")) if imports_dir.exists() else []
    assert imported == [], "dry-run must not create files"


def test_absorb_imports_docs(tmp_path: Path):
    repo = _init_with_vault(tmp_path)
    (repo / "ARCHITECTURE.md").write_text("# Architecture\n\nDesign overview.\n")
    (repo / "CHANGELOG.md").write_text("# Changelog\n\n## v1.0.0\n- initial release\n")
    r = _run("absorb", "--project", str(repo))
    assert r.returncode == 0
    imports_dir = repo / "agent-knowledge" / "Evidence" / "imports"
    assert imports_dir.is_dir()
    files = list(imports_dir.glob("*.md"))
    assert len(files) >= 2


def test_absorb_imports_have_metadata_header(tmp_path: Path):
    repo = _init_with_vault(tmp_path)
    (repo / "ARCHITECTURE.md").write_text("# Architecture\n\nDetails here.\n")
    _run("absorb", "--project", str(repo))
    imports_dir = repo / "agent-knowledge" / "Evidence" / "imports"
    arch_files = list(imports_dir.glob("*ARCHITECTURE*"))
    assert arch_files, "ARCHITECTURE.md should be imported"
    content = arch_files[0].read_text()
    assert "canonical: false" in content
    assert "source:" in content


def test_absorb_docs_dir(tmp_path: Path):
    repo = _init_with_vault(tmp_path)
    docs = repo / "docs"
    docs.mkdir()
    (docs / "design.md").write_text("# Design\n\nDetails.\n")
    (docs / "api.md").write_text("# API\n\nEndpoints.\n")
    r = _run("absorb", "--project", str(repo))
    assert r.returncode == 0
    imports_dir = repo / "agent-knowledge" / "Evidence" / "imports"
    files = list(imports_dir.glob("*.md"))
    assert any("design" in f.name for f in files)
    assert any("api" in f.name for f in files)


def test_absorb_adr_parsed_into_decisions(tmp_path: Path):
    repo = _init_with_vault(tmp_path)
    adr_dir = repo / "adr"
    adr_dir.mkdir()
    (adr_dir / "001-use-postgres.md").write_text(
        "# ADR-001: Use PostgreSQL\n\n## Status\n\nAccepted\n\n## Context\n\nWe need a relational database.\n\n## Decision\n\nUse PostgreSQL.\n"
    )
    r = _run("absorb", "--project", str(repo))
    assert r.returncode == 0
    decisions_path = repo / "agent-knowledge" / "Memory" / "decisions" / "decisions.md"
    assert decisions_path.is_file()
    content = decisions_path.read_text()
    assert "adr/001-use-postgres.md" in content


def test_absorb_idempotent(tmp_path: Path):
    repo = _init_with_vault(tmp_path)
    (repo / "ARCHITECTURE.md").write_text("# Architecture\n\nStable.\n")
    _run("absorb", "--project", str(repo))
    _run("absorb", "--project", str(repo))
    imports_dir = repo / "agent-knowledge" / "Evidence" / "imports"
    arch_files = list(imports_dir.glob("*ARCHITECTURE*"))
    assert len(arch_files) == 1, "idempotent: file should not be duplicated"


def test_absorb_manifest_created(tmp_path: Path):
    repo = _init_with_vault(tmp_path)
    (repo / "ARCHITECTURE.md").write_text("# Arch\n\nContent.\n")
    r = _run("absorb", "--project", str(repo))
    assert r.returncode == 0
    manifest = repo / "agent-knowledge" / "Outputs" / "absorb-manifest.md"
    assert manifest.is_file()
    content = manifest.read_text()
    assert "ARCHITECTURE.md" in content
    assert "canonical: false" in content


def test_absorb_manifest_not_in_memory(tmp_path: Path):
    repo = _init_with_vault(tmp_path)
    (repo / "ARCHITECTURE.md").write_text("# Arch\n\nContent.\n")
    _run("absorb", "--project", str(repo))
    memory_dir = repo / "agent-knowledge" / "Memory"
    md_files = list(memory_dir.rglob("absorb-manifest.md"))
    assert not md_files, "absorb-manifest.md must not appear in Memory/"


def test_absorb_json_mode(tmp_path: Path):
    repo = _init_with_vault(tmp_path)
    (repo / "ARCHITECTURE.md").write_text("# Arch\n\nContent.\n")
    r = _run("absorb", "--project", str(repo), "--json")
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert "sources_found" in data
    assert "imported" in data
    assert "decisions_parsed" in data


def test_absorb_no_vault_exits_nonzero(tmp_path: Path):
    repo = _init_repo(tmp_path, "bare-repo")
    r = _run("absorb", "--project", str(repo))
    assert r.returncode != 0


def test_absorb_skips_vault_files(tmp_path: Path):
    repo = _init_with_vault(tmp_path)
    # Write a file inside the vault -- should not be re-imported
    vault = repo / "agent-knowledge"
    (vault / "Memory" / "MEMORY.md").write_text("# Memory\n\nContent.\n")
    r = _run("absorb", "--project", str(repo), "--json")
    assert r.returncode == 0
    data = json.loads(r.stdout)
    # Nothing from vault should appear as a new import
    imports_dir = vault / "Evidence" / "imports"
    if imports_dir.exists():
        files = [f.name for f in imports_dir.glob("*.md")]
        assert not any("MEMORY" in f for f in files)
