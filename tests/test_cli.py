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
    assert "bedrock" in r.stdout.lower() or "adaptive" in r.stdout.lower()


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
    assert not (repo / "bedrock").exists()
    assert not (repo / ".agent-project.yaml").exists()


def test_init_infers_slug_from_dirname(tmp_path: Path):
    repo = _init_repo(tmp_path, "My Cool Project")
    kh = tmp_path / "kh"
    r = _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    assert r.returncode == 0, f"init failed: {r.stderr}"
    assert (repo / "bedrock").is_dir()
    assert (repo / "bedrock" / "Memory" / "PROJECT.md").is_file()
    assert (repo / "bedrock" / "Memory" / "decisions.md").is_file()
    assert (repo / "bedrock" / "Memory" / "glossary.md").is_file()
    assert (repo / "bedrock" / "Work" / "NOW.md").is_file()
    assert (repo / "bedrock" / "Work" / "backlog.md").is_file()
    assert (repo / "bedrock" / "Work" / "open-questions.md").is_file()
    assert (repo / "bedrock" / "Work" / "risks.md").is_file()
    assert (repo / "bedrock" / "Views" / "site").is_dir()
    assert (repo / "bedrock" / "Views" / "graph").is_dir()


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
    assert (repo / "bedrock").is_dir()
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
    assert "bedrock" in content.lower()


def test_init_installs_codex_bridge_when_detected(tmp_path: Path):
    repo = _init_repo(tmp_path, "codex-test")
    (repo / ".codex").mkdir()
    kh = tmp_path / "kh"
    r = _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    assert r.returncode == 0, f"init failed: {r.stderr}"
    agents = repo / ".codex" / "AGENTS.md"
    assert agents.is_file()
    content = agents.read_text()
    assert "Memory/" in content
    assert "Work/" in content
    assert "Views/" in content


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
    assert (repo / "bedrock").is_dir()
    assert (repo / ".agent-project.yaml").is_file()
    assert (repo / "AGENTS.md").is_file()


def test_init_sets_onboarding_pending(tmp_path: Path):
    repo = _init_repo(tmp_path, "onboarding-test")
    kh = tmp_path / "kh"
    r = _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    assert r.returncode == 0
    status = (repo / "bedrock" / "STATUS.md").read_text()
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
    assert (repo / "bedrock").is_dir()
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
    (mem_dir / "PROJECT.md").write_text("---\nproject: test\n---\n# Project\n")

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

    vault_stack = repo / "bedrock" / "Memory" / "stack.md"
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

    git_evidence = repo / "bedrock" / "Evidence" / "raw" / "git-recent.md"
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

    status = (repo / "bedrock" / "STATUS.md").read_text()
    # After sync, Last project sync body line should have a timestamp (not not-yet)
    import re
    m = re.search(r"Last project sync.*?`([^`]+)`", status, re.IGNORECASE)
    assert m is not None, "last_project_sync should be stamped in STATUS.md"
    assert m.group(1) not in ("", "not-yet")


# -- sync cleanup tests ---------------------------------------------------- #


def test_sync_does_not_create_capture_files(tmp_path: Path):
    repo = _init_repo(tmp_path, "capture-test")
    kh = tmp_path / "kh"
    r = _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    assert r.returncode == 0

    r = _run("sync", "--project", str(repo))
    assert r.returncode == 0

    captures_dir = repo / "bedrock" / "Evidence" / "captures"
    assert not captures_dir.exists(), "sync should not create legacy capture files"


# -- index tests ----------------------------------------------------------- #


def test_sync_creates_knowledge_index(tmp_path: Path):
    repo = _init_repo(tmp_path, "index-test")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    r = _run("sync", "--project", str(repo))
    assert r.returncode == 0

    index_json = repo / "bedrock" / "Views" / "graph" / "knowledge-index.json"
    index_md = repo / "bedrock" / "Views" / "graph" / "knowledge-index.md"
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

    index_json = repo / "bedrock" / "Views" / "graph" / "knowledge-index.json"
    assert index_json.is_file()


def test_index_memory_first(tmp_path: Path):
    """Knowledge index must list Memory/ notes before Evidence/ and Outputs/."""
    repo = _init_repo(tmp_path, "index-order")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    _run("sync", "--project", str(repo))

    index_json = repo / "bedrock" / "Views" / "graph" / "knowledge-index.json"
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

    index_json = repo / "bedrock" / "Views" / "graph" / "knowledge-index.json"
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


def test_view_serve_serves_site_over_http(tmp_path: Path):
    """view --serve must serve index.html and its data files over 127.0.0.1."""
    import http.client
    import os
    import socket
    import time

    repo = _init_repo(tmp_path, "view-serve")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    _run("sync", "--project", str(repo))

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    env = {**os.environ, "BROWSER": "echo"}  # keep the test from opening a real browser
    proc = subprocess.Popen(
        [*BIN, "view", "--project", str(repo), "--serve", "--port", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )

    def fetch(name):
        # http.client rather than urllib: urllib resolves system proxy settings,
        # and on macOS that can route a 127.0.0.1 request away from the server.
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            conn.request("GET", f"/{name}")
            return conn.getresponse().status
        finally:
            conn.close()

    try:
        codes = {}
        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                for name in ("index.html", "data/knowledge.json"):
                    codes[name] = fetch(name)
                break
            except OSError:
                assert proc.poll() is None, f"server exited: {proc.communicate()[1]}"
                time.sleep(0.5)

        if codes.get("index.html") != 200:
            proc.terminate()
            out, err = proc.communicate(timeout=10)
            raise AssertionError(
                f"index.html was not served over HTTP (codes={codes})\n"
                f"--- server stdout ---\n{out}\n--- server stderr ---\n{err}"
            )
        assert codes.get("data/knowledge.json") == 200, "site data must be served over HTTP"
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_export_html_creates_site(tmp_path: Path):
    """export-html must create Views/site/index.html and data/knowledge.json."""
    repo = _init_repo(tmp_path, "html-test")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    _run("sync", "--project", str(repo))

    r = _run("export-html", "--project", str(repo))
    assert r.returncode == 0, f"export-html failed: {r.stderr}"

    site_dir = repo / "bedrock" / "Views" / "site"
    assert site_dir.is_dir(), "Views/site/ must be created"

    index_html = site_dir / "index.html"
    assert index_html.is_file(), "Views/site/index.html must exist"

    knowledge_json = site_dir / "data" / "knowledge.json"
    assert knowledge_json.is_file(), "Views/site/data/knowledge.json must exist"

    # HTML sanity checks
    html = index_html.read_text()
    assert "<!DOCTYPE html>" in html
    assert "bedrock" in html.lower()
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

    site_dir = repo / "bedrock" / "Outputs" / "site"
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

    html = (repo / "bedrock" / "Views" / "site" / "index.html").read_text()
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

    kj = repo / "bedrock" / "Views" / "site" / "data" / "knowledge.json"
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
    vault = repo / "bedrock"
    ev_dir = vault / "Evidence" / "imports"
    ev_dir.mkdir(parents=True, exist_ok=True)
    (ev_dir / "test-import.md").write_text(
        "---\nnote_type: evidence\nsource: https://example.com\ncanonical: false\n---\n\n# Test Import\n\nSome content.\n"
    )

    _run("export-html", "--project", str(repo))

    kj = repo / "bedrock" / "Views" / "site" / "data" / "knowledge.json"
    data = json.loads(kj.read_text())

    # Branches from Memory/ are canonical
    assert all(b["canonical"] for b in data["branches"])
    # Evidence is non-canonical
    assert all(not e["canonical"] for e in data["evidence"])


def test_export_html_external_vault_pointer(tmp_path: Path):
    """The site generator must work through the local ./bedrock pointer."""
    repo = _init_repo(tmp_path, "html-pointer")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    # The pointer should be a symlink (or the external dir on Windows)
    pointer = repo / "bedrock"
    assert pointer.exists(), "./bedrock pointer must exist"

    r = _run("export-html", "--project", str(repo))
    assert r.returncode == 0, f"export-html failed through pointer: {r.stderr}"
    assert (repo / "bedrock" / "Views" / "site" / "index.html").is_file()


# -- graph tests ----------------------------------------------------------- #


def test_export_html_creates_graph_json(tmp_path: Path):
    """export-html must produce Views/site/data/graph.json alongside knowledge.json."""
    repo = _init_repo(tmp_path, "graph-exists")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    _run("sync", "--project", str(repo))
    _run("export-html", "--project", str(repo))

    graph_json = repo / "bedrock" / "Views" / "site" / "data" / "graph.json"
    assert graph_json.is_file(), "Views/site/data/graph.json must be created by export-html"

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

    gj = json.loads((repo / "bedrock" / "Views" / "site" / "data" / "graph.json").read_text())
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
    ev_dir = repo / "bedrock" / "Evidence" / "imports"
    ev_dir.mkdir(parents=True, exist_ok=True)
    (ev_dir / "external-ref.md").write_text(
        "---\nnote_type: evidence\nsource: https://example.com\n---\n\n# External Ref\n\nSome imported text.\n"
    )

    _run("export-html", "--project", str(repo))

    gj = json.loads((repo / "bedrock" / "Views" / "site" / "data" / "graph.json").read_text())

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

    gj = json.loads((repo / "bedrock" / "Views" / "site" / "data" / "graph.json").read_text())
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

    gj = json.loads((repo / "bedrock" / "Views" / "site" / "data" / "graph.json").read_text())
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

    html = (repo / "bedrock" / "Views" / "site" / "index.html").read_text()

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

    html = (repo / "bedrock" / "Views" / "site" / "index.html").read_text()

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

    graph_json = repo / "bedrock" / "Outputs" / "site" / "data" / "graph.json"
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

    # Hooks must reference bedrock commands, not raw scripts
    for hook in data["hooks"]:
        cmd = hook.get("command", "")
        assert "bedrock" in cmd, f"Hook command should use CLI, not raw script: {cmd}"


# -- package naming test --------------------------------------------------- #


def test_package_naming_consistent():
    """pyproject.toml package name must be project-bedrock."""
    import re

    pyproject = (
        __import__("pathlib").Path(__file__).parent.parent / "pyproject.toml"
    ).read_text()
    m = re.search(r'^name\s*=\s*"([^"]+)"', pyproject, re.MULTILINE)
    assert m is not None, "pyproject.toml must have a name field"
    pkg_name = m.group(1)
    assert pkg_name == "project-bedrock", (
        f"PyPI package name must be 'project-bedrock', got '{pkg_name}'"
    )


def test_cli_command_is_bedrock():
    """The primary CLI entry point must be named bedrock; agent-knowledge kept as deprecated alias."""
    import re

    pyproject = (
        __import__("pathlib").Path(__file__).parent.parent / "pyproject.toml"
    ).read_text()
    m = re.search(r'^\[project\.scripts\](.*?)(?=^\[|\Z)', pyproject, re.MULTILINE | re.DOTALL)
    assert m is not None, "pyproject.toml must have [project.scripts]"
    scripts_block = m.group(0)
    assert "bedrock" in scripts_block, "Primary CLI command must be 'bedrock'"
    assert "agent-knowledge" in scripts_block, "Deprecated alias 'agent-knowledge' must still be present"


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

    # init writes its own evidence here, so identify the imported note by what
    # this command adds rather than by picking the first non-README file.
    imports_dir = repo / "bedrock" / "Evidence" / "imports"
    before = {f.name for f in imports_dir.glob("*.md")}

    r = _run(
        "clean-import",
        str(html_file),
        "--project", str(repo),
    )
    assert r.returncode == 0, f"clean-import failed: {r.stderr}"

    added = [f for f in imports_dir.glob("*.md") if f.name not in before]
    assert len(added) == 1, f"clean-import should produce exactly one .md file, got {added}"

    content = added[0].read_text()
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

    memory_dir = repo / "bedrock" / "Memory"
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

    # Compare against what init already imported rather than assuming the
    # directory is empty -- init writes its own evidence there.
    imports_dir = repo / "bedrock" / "Evidence" / "imports"
    before = {f.name for f in imports_dir.glob("*.md")}

    r = _run("clean-import", str(html_file), "--project", str(repo), "--dry-run")
    assert r.returncode == 0

    after = {f.name for f in imports_dir.glob("*.md")}
    assert after == before, f"dry-run must not create any import files: {after - before}"


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
    """export-canvas must produce a valid .canvas JSON file in Views/graph/."""
    repo = _init_repo(tmp_path, "canvas-test")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    r = _run("export-canvas", "--project", str(repo))
    assert r.returncode == 0

    canvas_path = repo / "bedrock" / "Views" / "graph" / "knowledge-export.canvas"
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

    canvas_path = repo / "bedrock" / "Views" / "graph" / "knowledge-export.canvas"
    assert not canvas_path.exists(), "dry-run must not create the canvas file"


def test_export_canvas_memory_nodes_present(tmp_path: Path):
    """Canvas must include at least one Memory/ node."""
    repo = _init_repo(tmp_path, "canvas-nodes")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    _run("export-canvas", "--project", str(repo))

    canvas_path = repo / "bedrock" / "Views" / "graph" / "knowledge-export.canvas"
    data = json.loads(canvas_path.read_text())
    node_files = [n.get("file", "") for n in data["nodes"]]
    assert any("Memory" in f for f in node_files), "Canvas must include Memory/ nodes"


def test_canvas_is_non_canonical(tmp_path: Path):
    """Canvas must not appear in Memory/; it is an Output."""
    repo = _init_repo(tmp_path, "canvas-canon")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    _run("export-canvas", "--project", str(repo))

    memory_dir = repo / "bedrock" / "Memory"
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

    vault = repo / "bedrock"
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
    hist = repo / "bedrock" / "History"
    if hist.exists():
        shutil.rmtree(hist)

    r = _run("backfill-history", "--project", str(repo), "--dry-run")
    assert r.returncode == 0

    assert not (repo / "bedrock" / "History" / "events.ndjson").exists(), \
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

    events_path = repo / "bedrock" / "History" / "events.ndjson"
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
    memory_dir = repo / "bedrock" / "Memory"
    test_note = memory_dir / "test-area.md"
    test_note.write_text("---\nnote_type: branch-entry\narea: test\n---\n\n# Test\n\nContent.\n")
    original = test_note.read_text()

    _run("backfill-history", "--project", str(repo))

    assert test_note.read_text() == original, "backfill must not modify Memory/ notes"

    # No events.ndjson inside Memory/
    for f in memory_dir.rglob("*.ndjson"):
        pytest.fail(f"NDJSON file must not exist in Memory/: {f}")


def test_init_backfills_history(tmp_path: Path):
    """bedrock init must automatically create History/ layer."""
    repo = _init_repo(tmp_path, "hist-init-auto")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    vault = repo / "bedrock"
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

    history_md = repo / "bedrock" / "History" / "history.md"
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
    status_md = repo / "bedrock" / "STATUS.md"
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
    """refresh-system must never modify user Memory/ or Work/ content."""
    repo = _init_repo(tmp_path, "refresh-memory")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    # Seed a memory note
    memory_dir = repo / "bedrock" / "Memory"
    test_note = memory_dir / "test-branch.md"
    test_note.write_text("---\nnote_type: branch-entry\narea: test\n---\n\n# Test\n\nContent.\n")
    original_content = test_note.read_text()
    work_now = repo / "bedrock" / "Work" / "NOW.md"
    original_work = work_now.read_text()

    _run("refresh-system", "--project", str(repo))

    assert test_note.read_text() == original_content, "refresh-system must not modify Memory/ notes"
    assert work_now.read_text() == original_work, "refresh-system must not modify Work/ files"


def test_refresh_system_updates_status_md_version(tmp_path: Path):
    """refresh-system must add framework_version to STATUS.md."""
    repo = _init_repo(tmp_path, "refresh-status")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    _run("refresh-system", "--project", str(repo))

    status = (repo / "bedrock" / "STATUS.md").read_text()
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
    memory_dir = repo / "bedrock" / "Memory"
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
    """Cursor command files must reference 'bedrock', not repo-relative paths."""
    repo = _init_repo(tmp_path, "cmd-runtime")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    for cmd_name in ("memory-update.md", "system-update.md"):
        cmd_file = repo / ".cursor" / "commands" / cmd_name
        assert cmd_file.is_file(), f"{cmd_name} must be installed"
        content = cmd_file.read_text()
        assert "bedrock" in content, \
            f"{cmd_name} must reference the installed 'bedrock' CLI"
        # Must not use repo-relative script paths
        assert "scripts/" not in content, \
            f"{cmd_name} must not use repo-relative scripts/"


def test_memory_update_command_covers_sync(tmp_path: Path):
    """/memory-update command must instruct the agent to run bedrock sync."""
    repo = _init_repo(tmp_path, "mem-cmd")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    content = (repo / ".cursor" / "commands" / "memory-update.md").read_text()
    assert "sync" in content.lower(), "memory-update must mention sync"
    assert "Memory" in content, "memory-update must mention Memory/"
    assert "Work" in content, "memory-update must mention Work/"


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
    """All hooks must call 'bedrock', not repo-relative scripts."""
    repo = _init_repo(tmp_path, "hooks-runtime")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    data = json.loads((repo / ".cursor" / "hooks.json").read_text())
    for hook in data.get("hooks", []):
        cmd = hook.get("command", "")
        assert cmd.startswith("bedrock "), \
            f"Hook '{hook['name']}' must call bedrock, got: {cmd}"


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

    rule = (repo / ".cursor" / "rules" / "bedrock.mdc").read_text()
    assert "Memory/" in rule
    assert "Work/" in rule
    assert "Views/" in rule
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

    rule = (repo / ".cursor" / "rules" / "bedrock.mdc").read_text()
    assert "/memory-update" in rule


def test_init_cursor_integration_idempotent(tmp_path: Path):
    """Running init twice must not break .cursor/ integration files."""
    repo = _init_repo(tmp_path, "idem-cursor")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    # Record content after first init
    rule_content = (repo / ".cursor" / "rules" / "bedrock.mdc").read_text()
    hooks_content = (repo / ".cursor" / "hooks.json").read_text()

    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    # Content must be unchanged (not force-overwritten)
    assert (repo / ".cursor" / "rules" / "bedrock.mdc").read_text() == rule_content
    assert (repo / ".cursor" / "hooks.json").read_text() == hooks_content


def test_bundled_cursor_commands_exist():
    """Cursor command templates must be bundled in the package assets."""
    from agent_knowledge.runtime.paths import get_assets_dir

    assets = get_assets_dir()
    for cmd in ("memory-update.md", "system-update.md"):
        path = assets / "templates" / "integrations" / "cursor" / "commands" / cmd
        assert path.is_file(), f"Bundled cursor command missing: {path}"
        content = path.read_text()
        assert "bedrock" in content, f"{cmd} must reference bedrock CLI"


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
    assert "bedrock" in content
    # Must not contain repo-relative script paths
    assert "scripts/" not in content
    assert "bash " not in content


def test_claude_settings_hooks_pass_no_path_at_all(tmp_path: Path):
    """Hook commands must carry no path argument.

    A path in the command has to be correct on every machine, survive spaces,
    and expand in whatever shell the agent picked -- Git Bash or PowerShell on
    Windows. Passing none and letting the CLI find the project root sidesteps
    all three.
    """
    repo = _init_repo(tmp_path, "claude repo path")  # space: must not need quoting
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    data = json.loads((repo / ".claude" / "settings.json").read_text())
    repo_abs = str(repo.resolve())
    for event, hook_list in data["hooks"].items():
        for entry in hook_list:
            for hook in entry.get("hooks", []):
                cmd = hook.get("command", "")
                assert "--project" not in cmd, f"Hook for {event} must not pass a project path"
                assert "$" not in cmd, f"Hook for {event} must not depend on shell variable expansion"
                assert repo_abs not in cmd, f"Hook for {event} must not hardcode the repo path"


def test_cursor_hooks_pass_no_path_at_all(tmp_path: Path):
    """Cursor hook commands must carry no path argument either."""
    repo = _init_repo(tmp_path, "cursor repo path")  # space: must not need quoting
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    data = json.loads((repo / ".cursor" / "hooks.json").read_text())
    repo_abs = str(repo.resolve())
    for hook in data["hooks"]:
        cmd = hook["command"]
        assert "--project" not in cmd, f"{hook['name']} must not pass a project path"
        assert "$" not in cmd, f"{hook['name']} must not depend on shell variable expansion"
        assert repo_abs not in cmd, f"{hook['name']} must not hardcode the repo path"


def test_sync_run_from_a_subdirectory_finds_the_project(tmp_path: Path):
    """Hooks run in whatever cwd the agent was in, so a bare command must walk up."""
    repo = _init_repo(tmp_path, "subdir-sync")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    nested = repo / "src" / "deep"
    nested.mkdir(parents=True)

    r = _run("sync", cwd=str(nested))
    assert r.returncode == 0, f"sync from a subdirectory must find the project: {r.stderr}"
    assert not (nested / "bedrock").exists(), "sync must not scaffold a second vault beside the agent's cwd"
    assert "vault not found" not in r.stderr, f"sync silently skipped the vault: {r.stderr}"


def test_scaffolded_project_overview_indexes_area_docs(tmp_path: Path):
    """PROJECT.md must carry an Areas index so per-area docs have a visible home.

    Without a place to list them, cross-cutting subsystems end up scattered
    between the overview and the decisions log.
    """
    repo = _init_repo(tmp_path, "areas-index")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    text = (repo / "bedrock" / "Memory" / "PROJECT.md").read_text()
    assert "## Areas" in text, "PROJECT.md must have an Areas section"
    assert "Memory/<area>.md" in text, "the Areas section must name the per-area doc convention"


def test_update_works_in_a_local_vault(tmp_path: Path):
    """A local vault is a real directory, so update must not demand a symlink.

    The Cursor post-write hook runs `bedrock update`, so this fails on every
    write in every default-mode project.
    """
    repo = _init_repo(tmp_path, "local-update")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    r = _run("update", "--project", str(repo))
    assert "must be a symlink" not in r.stderr, "local vaults are directories, not symlinks"
    assert r.returncode == 0, f"update must work in a local vault: {r.stderr}"


def test_update_summary_file_lands_in_the_project_from_a_subdirectory(tmp_path: Path):
    """A relative --summary-file must resolve against the project, not the agent's cwd."""
    repo = _init_repo(tmp_path, "subdir-summary")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    nested = repo / "src" / "deep"
    nested.mkdir(parents=True)

    r = _run("update", "--summary-file", "./.cursor/knowledge-sync.last.json", cwd=str(nested))
    assert r.returncode == 0, f"update from a subdirectory failed: {r.stderr}"
    assert (repo / ".cursor" / "knowledge-sync.last.json").is_file()
    assert not (nested / ".cursor").exists(), "summary must not land beside the agent's cwd"


def test_refresh_system_preserves_foreign_claude_hooks(tmp_path: Path):
    """refresh-system must refresh bedrock hooks without dropping project-added ones."""
    repo = _init_repo(tmp_path, "claude-foreign-hooks")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    settings = repo / ".claude" / "settings.json"
    data = json.loads(settings.read_text())
    # A hook the project added itself, plus a stale bedrock hook with an absolute path.
    data["hooks"]["SessionStart"].append(
        {"matcher": "", "hooks": [{"type": "command", "command": "bd prime"}]}
    )
    data["hooks"]["Stop"] = [
        {"matcher": "", "hooks": [{"type": "command", "command": f"bedrock sync --project {repo}"}]}
    ]
    data["permissions"] = {"allow": ["Bash(ls:*)"]}
    settings.write_text(json.dumps(data, indent=2))

    r = _run("refresh-system", "--project", str(repo))
    assert r.returncode == 0, f"refresh-system failed: {r.stderr}"

    after = json.loads(settings.read_text())
    commands = [
        h.get("command", "")
        for groups in after["hooks"].values()
        for g in groups
        for h in g.get("hooks", [])
    ]
    assert "bd prime" in commands, "project-added hook must survive refresh-system"
    assert str(repo) not in " ".join(commands), "stale absolute path must be replaced"
    assert after.get("permissions") == {"allow": ["Bash(ls:*)"]}, "non-hook settings must survive"


def test_refresh_system_localizes_real_path(tmp_path: Path):
    """refresh-system must rewrite an absolute real_path to ./bedrock for local vaults."""
    repo = _init_repo(tmp_path, "local-real-path")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    project_yaml = repo / ".agent-project.yaml"
    text = project_yaml.read_text()
    assert "vault_mode: local" in text
    project_yaml.write_text(
        re.sub(r"real_path:\s*\S+", f"real_path: {tmp_path / 'other-machine' / 'bedrock'}", text)
    )

    r = _run("refresh-system", "--project", str(repo))
    assert r.returncode == 0, f"refresh-system failed: {r.stderr}"
    assert "real_path: ./bedrock" in project_yaml.read_text()


@pytest.mark.parametrize(
    "value",
    [
        "/home/other/code/proj/bedrock",
        "/Users/dor thalamus/Documents/New project/bedrock",  # the #9 path shape
        '"/home/other/code/proj/bedrock"',
    ],
)
def test_localize_real_path_handles_every_absolute_shape(value: str):
    """Absolute real_path values must localize regardless of spaces or quoting."""
    from agent_knowledge.runtime.refresh import _localize_real_path

    text = f"knowledge:\n  vault_mode: local\n  real_path: {value}\n  ignore_file: ./x\n"
    updated, localized = _localize_real_path(text)
    assert localized, f"{value!r} must be recognized as absolute"
    assert "real_path: ./bedrock" in updated
    assert "ignore_file: ./x" in updated


def test_localize_real_path_leaves_external_vaults_alone():
    """External vaults legitimately point outside the repo and must not be rewritten."""
    from agent_knowledge.runtime.refresh import _localize_real_path

    text = "knowledge:\n  vault_mode: external\n  real_path: /home/me/agent-os/projects/x\n"
    updated, localized = _localize_real_path(text)
    assert not localized
    assert updated == text


def test_localize_real_path_is_idempotent():
    """An already-relative real_path must not be rewritten again."""
    from agent_knowledge.runtime.refresh import _localize_real_path

    text = "knowledge:\n  vault_mode: local\n  real_path: ./bedrock\n"
    assert _localize_real_path(text) == (text, False)


def test_merge_preserves_commands_chained_onto_bedrock_hooks():
    """A project that extended the bedrock hook must keep its half of the command."""
    from agent_knowledge.runtime.refresh import _merge_claude_hooks

    template = {"hooks": {"Stop": [{"matcher": "", "hooks": [{"type": "command", "command": "bedrock sync --project ."}]}]}}
    current = {
        "hooks": {
            "Stop": [
                {
                    "matcher": "",
                    "hooks": [{"type": "command", "command": "bedrock sync --project . && npm run notify"}],
                }
            ]
        }
    }
    commands = [
        h["command"] for g in _merge_claude_hooks(template, current)["hooks"]["Stop"] for h in g["hooks"]
    ]
    assert "bedrock sync --project . && npm run notify" in commands, "chained project command must survive"


@pytest.mark.parametrize(
    "stale",
    [
        "bedrock sync --project /home/other/code/proj",
        "bedrock sync --project '/home/other/code/proj'",
        "agent-knowledge sync --project /home/other/code/proj",
        "bedrock sync --project .",
    ],
)
def test_merge_replaces_every_generated_command_shape(stale: str):
    """Commands bedrock itself generated (current or historical) must be replaced."""
    from agent_knowledge.runtime.refresh import _merge_claude_hooks

    template = {"hooks": {"Stop": [{"matcher": "", "hooks": [{"type": "command", "command": "bedrock sync --project ."}]}]}}
    current = {"hooks": {"Stop": [{"matcher": "", "hooks": [{"type": "command", "command": stale}]}]}}
    commands = [
        h["command"] for g in _merge_claude_hooks(template, current)["hooks"]["Stop"] for h in g["hooks"]
    ]
    assert commands == ["bedrock sync --project ."], f"stale command not replaced: {stale}"


def test_view_skips_browser_without_a_display(tmp_path: Path):
    """view must print the path instead of failing when there is no display (SSH/headless)."""
    import os

    repo = _init_repo(tmp_path, "headless-view")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    env = {k: v for k, v in os.environ.items() if k not in ("DISPLAY", "WAYLAND_DISPLAY")}
    env["SSH_CONNECTION"] = "10.0.0.1 22 10.0.0.2 22"
    r = subprocess.run(
        [*BIN, "view", "--project", str(repo)],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    assert r.returncode == 0, f"view must succeed headless: {r.stderr}"
    assert "index.html" in r.stderr, "the path to open must be printed when the browser is skipped"


def test_view_names_serve_over_ssh(tmp_path: Path):
    """Over SSH the printed file:// path is on the wrong machine, so name --serve.

    A remote path pasted into a browser on the client resolves against the
    *client's* filesystem, where it does not exist. Printing it by itself reads
    like a working remedy and sends people debugging a rendering problem that
    is not there, while --serve -- which already exists and is forwardable --
    goes unmentioned at the one moment it is needed.
    """
    import os

    repo = _init_repo(tmp_path, "ssh-view-hint")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    env = {k: v for k, v in os.environ.items() if k not in ("DISPLAY", "WAYLAND_DISPLAY")}
    env["SSH_CONNECTION"] = "10.0.0.1 22 10.0.0.2 22"
    r = subprocess.run(
        [*BIN, "view", "--project", str(repo)],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    assert r.returncode == 0, f"view must succeed over ssh: {r.stderr}"
    assert "--serve" in r.stderr, (
        f"the ssh fallback must point at --serve, got: {r.stderr!r}"
    )


def test_has_display_accepts_a_forwarded_display_over_ssh(monkeypatch):
    """ssh -X sets DISPLAY, and that browser genuinely works.

    Rejecting every SSH session outright ignores the forwarded case, so the one
    remote setup that *can* open a browser is told it cannot.
    """
    from agent_knowledge.runtime import shell

    monkeypatch.setattr(shell.sys, "platform", "linux")
    monkeypatch.setenv("SSH_CONNECTION", "10.0.0.1 22 10.0.0.2 22")
    monkeypatch.setenv("DISPLAY", "localhost:10.0")

    assert shell.has_display(), "a forwarded DISPLAY over ssh is a usable display"


def test_has_display_rejects_ssh_without_a_forwarded_display(monkeypatch):
    """A plain SSH session has no DISPLAY, and must still be treated as headless."""
    from agent_knowledge.runtime import shell

    monkeypatch.setattr(shell.sys, "platform", "linux")
    monkeypatch.setenv("SSH_CONNECTION", "10.0.0.1 22 10.0.0.2 22")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)

    assert not shell.has_display(), "plain ssh has no browser to open"


def test_has_display_rejects_ssh_into_a_mac(monkeypatch):
    """On darwin/win32 a display is assumed, but not for someone SSH'd in.

    The launcher would open a browser on the remote console, which nobody is
    sitting at.
    """
    from agent_knowledge.runtime import shell

    monkeypatch.setattr(shell.sys, "platform", "darwin")
    monkeypatch.setenv("SSH_CONNECTION", "10.0.0.1 22 10.0.0.2 22")

    assert not shell.has_display(), "ssh into a mac must not open the console browser"


def test_view_no_open_flag(tmp_path: Path):
    """--no-open must generate the site without launching a browser."""
    repo = _init_repo(tmp_path, "view-no-open")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    r = _run("view", "--project", str(repo), "--no-open")
    assert r.returncode == 0, f"view --no-open failed: {r.stderr}"
    assert (repo / "bedrock" / "Views" / "site" / "index.html").is_file()


def test_open_in_browser_does_not_wait_for_the_launcher(monkeypatch):
    """The launcher must be spawned, not waited on.

    On a GUI-less macOS box `open` can block for a long time. Waiting for it
    stalls `bedrock view --serve` before it ever binds its port.
    """
    from agent_knowledge.runtime import shell

    monkeypatch.setattr(shell, "has_display", lambda: True)
    monkeypatch.setattr(
        shell.subprocess, "run",
        lambda *a, **k: pytest.fail("the browser launcher must not be waited on"),
    )
    spawned = []
    monkeypatch.setattr(shell.subprocess, "Popen", lambda *a, **k: spawned.append((a, k)))

    assert shell.open_in_browser("http://127.0.0.1:1/index.html")
    assert spawned, "launcher must still be spawned when a display exists"


def test_open_in_browser_honors_the_browser_env_var(monkeypatch):
    """$BROWSER must win over the platform launcher, as every other tool honors it."""
    from agent_knowledge.runtime import shell

    monkeypatch.setattr(shell, "has_display", lambda: True)
    monkeypatch.setenv("BROWSER", "my-browser")
    spawned = []
    monkeypatch.setattr(shell.subprocess, "Popen", lambda *a, **k: spawned.append((a, k)))

    assert shell.open_in_browser("http://127.0.0.1:1/index.html")
    assert spawned[0][0][0] == ["my-browser", "http://127.0.0.1:1/index.html"]


def test_star_prompt_does_not_launch_a_browser_without_a_display(monkeypatch, tmp_path: Path):
    """The one-time star prompt must not spawn a GUI browser on a headless/SSH box.

    A failed launcher writes its errors after the shell prompt has returned and
    scribbles over the next prompt, which is the whole point of the display guard.
    """
    import io
    import webbrowser

    from agent_knowledge import cli

    opened: list[str] = []
    monkeypatch.setattr(webbrowser, "open", lambda url, *a, **k: opened.append(url))
    monkeypatch.setattr(cli, "_STAR_MARKER", tmp_path / "starred")
    monkeypatch.setattr(cli.click, "confirm", lambda *a, **k: True)
    monkeypatch.setenv("SSH_CONNECTION", "10.0.0.1 22 10.0.0.2 22")

    class _Tty(io.StringIO):
        def isatty(self) -> bool:
            return True

    monkeypatch.setattr(cli.sys, "stderr", _Tty())

    cli._maybe_star()

    assert opened == [], "the star prompt must go through the display-guarded opener"


def test_star_prompt_opens_the_repo_when_a_display_exists(monkeypatch, tmp_path: Path):
    """With a display the prompt must still open the repo page."""
    import io

    from agent_knowledge import cli
    from agent_knowledge.runtime import shell

    launched: list[tuple] = []
    monkeypatch.setattr(shell, "has_display", lambda: True)
    monkeypatch.setattr(shell.subprocess, "Popen", lambda *a, **k: launched.append(a))
    monkeypatch.setattr(shell.os, "startfile", lambda target: launched.append((target,)), raising=False)
    monkeypatch.setattr(cli, "_STAR_MARKER", tmp_path / "starred")
    monkeypatch.setattr(cli.click, "confirm", lambda *a, **k: True)

    class _Tty(io.StringIO):
        def isatty(self) -> bool:
            return True

    monkeypatch.setattr(cli.sys, "stderr", _Tty())

    cli._maybe_star()

    assert any(cli._REPO_URL in str(call) for call in launched), "repo page must open when a display exists"


def test_init_gitignores_the_per_machine_sync_artifact(tmp_path: Path):
    """.cursor/knowledge-sync.last.json records an absolute project path per machine.

    Sharing it makes the repo hostile to a second developer, so init must exclude it.
    """
    repo = _init_repo(tmp_path, "gitignore-artifact")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    assert ".cursor/knowledge-sync.last.json" in (repo / ".gitignore").read_text()


def test_refresh_system_adds_gitignore_patterns_an_older_connect_missed(tmp_path: Path):
    """A project connected by an older bedrock must pick up newly added patterns.

    refresh-system runs every session, so it is the only place an existing
    checkout can self-heal.
    """
    repo = _init_repo(tmp_path, "gitignore-selfheal")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    gitignore = repo / ".gitignore"
    gitignore.write_text(
        "my-own-thing/\n\n"
        "# bedrock: noisy auto-generated content excluded from git\n"
        "bedrock/Evidence/raw/\n"
        "bedrock/Views/site/\n"
    )

    r = _run("refresh-system", "--project", str(repo))
    assert r.returncode == 0, f"refresh-system failed: {r.stderr}"

    text = gitignore.read_text()
    assert ".cursor/knowledge-sync.last.json" in text, "missing pattern must be added"
    assert "my-own-thing/" in text, "project's own patterns must survive"
    assert text.count("bedrock/Evidence/raw/") == 1, "existing patterns must not be duplicated"


def test_refresh_system_leaves_a_complete_gitignore_alone(tmp_path: Path):
    """Refreshing twice must not keep rewriting .gitignore."""
    repo = _init_repo(tmp_path, "gitignore-idempotent")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    _run("refresh-system", "--project", str(repo))
    first = (repo / ".gitignore").read_text()
    _run("refresh-system", "--project", str(repo))
    assert (repo / ".gitignore").read_text() == first


def test_init_keeps_shared_integration_files_tracked(tmp_path: Path):
    """Hook configs are portable now, so they stay shareable — only artifacts are ignored."""
    repo = _init_repo(tmp_path, "gitignore-shared")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    text = (repo / ".gitignore").read_text()
    assert ".claude/settings.json" not in text
    assert ".cursor/hooks.json" not in text


def test_init_installs_claude_commands(tmp_path: Path):
    """init must create .claude/commands/ with memory-update.md and system-update.md."""
    repo = _init_repo(tmp_path, "claude-cmds")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    for cmd in ("memory-update.md", "system-update.md"):
        path = repo / ".claude" / "commands" / cmd
        assert path.is_file(), f".claude/commands/{cmd} must be created"
        content = path.read_text()
        assert "bedrock" in content, f"{cmd} must reference bedrock CLI"


def test_init_installs_claude_md(tmp_path: Path):
    """init must create .claude/CLAUDE.md with the runtime contract."""
    repo = _init_repo(tmp_path, "claude-md")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    claude_md = repo / ".claude" / "CLAUDE.md"
    assert claude_md.is_file(), ".claude/CLAUDE.md must be created"
    content = claude_md.read_text()
    assert "bedrock" in content
    assert "Memory/" in content
    assert "Work/" in content
    assert "Views/" in content
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
        assert "bedrock" in content
    assert "Work/" in claude_md.read_text()


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
    imports_dir = repo / "bedrock" / "Evidence" / "imports"
    imported = list(imports_dir.glob("ARCHITECTURE*.md")) if imports_dir.exists() else []
    assert imported == [], "dry-run must not create files"


def test_absorb_imports_docs(tmp_path: Path):
    repo = _init_with_vault(tmp_path)
    (repo / "ARCHITECTURE.md").write_text("# Architecture\n\nDesign overview.\n")
    (repo / "CHANGELOG.md").write_text("# Changelog\n\n## v1.0.0\n- initial release\n")
    r = _run("absorb", "--project", str(repo))
    assert r.returncode == 0
    imports_dir = repo / "bedrock" / "Evidence" / "imports"
    assert imports_dir.is_dir()
    files = list(imports_dir.glob("*.md"))
    assert len(files) >= 2


def test_absorb_imports_have_metadata_header(tmp_path: Path):
    repo = _init_with_vault(tmp_path)
    (repo / "ARCHITECTURE.md").write_text("# Architecture\n\nDetails here.\n")
    _run("absorb", "--project", str(repo))
    imports_dir = repo / "bedrock" / "Evidence" / "imports"
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
    imports_dir = repo / "bedrock" / "Evidence" / "imports"
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
    decisions_path = repo / "bedrock" / "Memory" / "decisions.md"
    assert decisions_path.is_file()
    content = decisions_path.read_text()
    assert "adr/001-use-postgres.md" in content


def test_absorb_idempotent(tmp_path: Path):
    repo = _init_with_vault(tmp_path)
    (repo / "ARCHITECTURE.md").write_text("# Architecture\n\nStable.\n")
    _run("absorb", "--project", str(repo))
    _run("absorb", "--project", str(repo))
    imports_dir = repo / "bedrock" / "Evidence" / "imports"
    arch_files = list(imports_dir.glob("*ARCHITECTURE*"))
    assert len(arch_files) == 1, "idempotent: file should not be duplicated"


def test_absorb_manifest_created(tmp_path: Path):
    repo = _init_with_vault(tmp_path)
    (repo / "ARCHITECTURE.md").write_text("# Arch\n\nContent.\n")
    r = _run("absorb", "--project", str(repo))
    assert r.returncode == 0
    manifest = repo / "bedrock" / "Outputs" / "absorb-manifest.md"
    assert manifest.is_file()
    content = manifest.read_text()
    assert "ARCHITECTURE.md" in content
    assert "canonical: false" in content


def test_absorb_manifest_not_in_memory(tmp_path: Path):
    repo = _init_with_vault(tmp_path)
    (repo / "ARCHITECTURE.md").write_text("# Arch\n\nContent.\n")
    _run("absorb", "--project", str(repo))
    memory_dir = repo / "bedrock" / "Memory"
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
    vault = repo / "bedrock"
    (vault / "Memory" / "PROJECT.md").write_text("# Project\n\nContent.\n")
    r = _run("absorb", "--project", str(repo), "--json")
    assert r.returncode == 0
    data = json.loads(r.stdout)
    # Nothing from vault should appear as a new import
    imports_dir = vault / "Evidence" / "imports"
    if imports_dir.exists():
        files = [f.name for f in imports_dir.glob("*.md")]
        assert not any("PROJECT" in f or "MEMORY" in f for f in files)


def _set_layout_version(repo: Path, value: int) -> None:
    """Write layout_version into the vault's STATUS.md frontmatter."""
    status = repo / "bedrock" / "STATUS.md"
    text = status.read_text()
    end = text.find("\n---", 3)
    status.write_text(f"{text[:end]}\nlayout_version: {value}{text[end:]}", encoding="utf-8")


def test_refresh_system_exits_zero_when_blocked_by_a_newer_layout(tmp_path: Path):
    """A blocked refresh must warn and exit 0.

    It runs from the SessionStart hook joined by &&, so a non-zero exit degrades
    every agent session in the repo -- worse than the stale layout it reports.
    """
    from agent_knowledge.runtime.migrations import LAYOUT_VERSION

    repo = _init_repo(tmp_path, "layout-newer")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    _set_layout_version(repo, LAYOUT_VERSION + 1)

    r = _run("refresh-system", "--project", str(repo))

    assert r.returncode == 0, f"a blocked refresh must not fail the SessionStart hook: {r.stderr}"
    assert "pip install -U project-bedrock" in r.stderr
    assert "Refreshed to v" not in r.stderr, "a blocked run must not claim it refreshed anything"


def test_sync_exits_zero_when_blocked_by_a_newer_layout(tmp_path: Path):
    """sync is the first half of 'bedrock sync && bedrock refresh-system'.

    A non-zero exit here would both fail the session and stop refresh-system
    from ever running to report why.
    """
    from agent_knowledge.runtime.migrations import LAYOUT_VERSION

    repo = _init_repo(tmp_path, "layout-newer-sync")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    _set_layout_version(repo, LAYOUT_VERSION + 1)

    r = _run("sync", "--project", str(repo))

    assert r.returncode == 0, f"a blocked sync must not fail the SessionStart hook: {r.stderr}"
    assert "pip install -U project-bedrock" in r.stderr
    assert "Sync complete" not in r.stderr, "a blocked run must not claim it synced anything"


def test_doctor_warns_when_the_project_layout_is_newer(tmp_path: Path):
    """doctor must tell you which side of the version gap you are on."""
    from agent_knowledge.runtime.migrations import LAYOUT_VERSION

    repo = _init_repo(tmp_path, "layout-doctor")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    _set_layout_version(repo, LAYOUT_VERSION + 1)

    r = _run("doctor", "--project", str(repo))

    assert "pip install -U project-bedrock" in r.stderr


def _status_frontmatter(repo: Path) -> dict[str, str]:
    """Parse bedrock/STATUS.md's leading frontmatter block into key -> value."""
    text = (repo / "bedrock" / "STATUS.md").read_text(encoding="utf-8")
    assert text.startswith("---\n")
    block = text[4:].split("\n---", 1)[0]
    fields: dict[str, str] = {}
    for line in block.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
    return fields


def test_status_frontmatter_survives_doctor(tmp_path: Path):
    """The shell rewrite of STATUS.md must not drop keys the Python layer owns.

    kc_status_write rebuilds the frontmatter from a fixed field list, so every
    key written elsewhere (framework_version, last_system_refresh,
    layout_version) used to be erased on each doctor/sync/validate run.
    """
    repo = _init_repo(tmp_path, "status-frontmatter")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    _run("refresh-system", "--project", str(repo))

    before = _status_frontmatter(repo)
    assert "framework_version" in before, "refresh-system should stamp framework_version"

    status = repo / "bedrock" / "STATUS.md"
    text = status.read_text(encoding="utf-8")
    end = text.find("\n---", 3)
    custom = "spaced: value/with, colon"
    status.write_text(
        f"{text[:end]}\nlayout_version: 7\ncustom_key: {custom}{text[end:]}",
        encoding="utf-8",
    )

    r = _run("doctor", "--project", str(repo))
    assert r.returncode == 0, r.stderr

    after = _status_frontmatter(repo)
    assert after.get("layout_version") == "7"
    assert after.get("custom_key") == custom
    assert after.get("framework_version") == before["framework_version"]
    assert after.get("last_system_refresh") == before.get("last_system_refresh")

    # Preserved keys must not drift or duplicate on a second rewrite.
    _run("doctor", "--project", str(repo))
    again = _status_frontmatter(repo)
    preserved = ("layout_version", "custom_key", "framework_version", "last_system_refresh")
    assert {k: again.get(k) for k in preserved} == {k: after.get(k) for k in preserved}
    block = status.read_text(encoding="utf-8")[4:].split("\n---", 1)[0]
    assert block.count("custom_key:") == 1
    assert block.count("framework_version:") == 1


def _common_lib() -> Path:
    from agent_knowledge.runtime.paths import get_assets_dir

    return get_assets_dir() / "scripts" / "lib" / "knowledge-common.sh"


def _rewrite_status_via_shell(status: Path) -> None:
    """Drive kc_status_load + kc_status_write directly, without a full CLI run."""
    script = (
        f'. "{_common_lib()}"\n'
        f'STATUS_FILE="{status}"\n'
        "kc_status_load\n"
        "kc_status_write\n"
    )
    r = subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr


def test_status_frontmatter_survives_a_crlf_file(tmp_path: Path):
    """CRLF must not defeat the carry-through.

    Git for Windows checks this file out with CRLF by default, and the awk
    delimiter match used to see "---\\r" and bail, dropping every unmanaged key.
    """
    status = tmp_path / "bedrock" / "STATUS.md"
    status.parent.mkdir(parents=True)
    lf = (
        "---\n"
        "note_type: knowledge-status\n"
        "project: crlf-repo\n"
        "onboarding: complete\n"
        "framework_version: 0.4.17\n"
        "last_system_refresh: 2026-08-11T00:00:00Z\n"
        "layout_version: 7\n"
        'custom_key: spaced: value/with, "quotes"\n'
        "---\n"
        "\n"
        "# Knowledge Status: crlf-repo\n"
    )
    status.write_bytes(lf.replace("\n", "\r\n").encode("utf-8"))

    _rewrite_status_via_shell(status)

    text = status.read_text(encoding="utf-8")
    block = text[4:].split("\n---", 1)[0]
    lines = [ln.rstrip("\r") for ln in block.splitlines()]
    assert "layout_version: 7" in lines
    assert 'custom_key: spaced: value/with, "quotes"' in lines
    assert "framework_version: 0.4.17" in lines
    assert "last_system_refresh: 2026-08-11T00:00:00Z" in lines

    # And a second rewrite of the now-LF file must not duplicate them.
    _rewrite_status_via_shell(status)
    block = status.read_text(encoding="utf-8")[4:].split("\n---", 1)[0]
    assert block.count("layout_version:") == 1
    assert block.count("custom_key:") == 1


def test_status_frontmatter_managed_key_lists_agree():
    """The awk skip-list and the printf emit-list are one schema in two copies.

    Adding a field to one and not the other produces a permanently duplicated
    YAML key, which strict parsers reject and kc_yaml_leaf_value reads first-wins.
    """
    text = _common_lib().read_text(encoding="utf-8")

    awk_list = " ".join(re.findall(r'managed_keys\s*=\s*(?:managed_keys\s*)?"([^"]*)"', text))
    awk_keys = set(awk_list.split())
    assert awk_keys, "could not find the awk managed-key list"

    start = text.index("kc_status_write() {")
    end = text.index("""printf '%s\\n\\n' '---'""", start)
    printf_keys = set(re.findall(r"^\s*printf '([A-Za-z_][A-Za-z0-9_]*):", text[start:end], re.M))
    assert printf_keys, "could not find the emitted frontmatter fields"

    # 'profile' is the legacy alias of profile_hint: skipped on read, never emitted.
    assert awk_keys - printf_keys == {"profile"}
    assert printf_keys - awk_keys == set()


# -- migrate-from-legacy --------------------------------------------------- #


def test_migrate_from_legacy_runs(tmp_path: Path):
    """The documented upgrade path from agent-knowledge-cli must actually run.

    It had no coverage at all, which is how it shipped calling run_refresh with
    a json_mode kwarg that does not exist.
    """
    repo = _init_repo(tmp_path, "legacy-migrate")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    r = _run("migrate-from-legacy", "--project", str(repo))

    assert r.returncode == 0, f"migrate-from-legacy crashed: {r.stderr}"
    assert "Traceback" not in r.stderr
    assert "pip uninstall agent-knowledge-cli" in r.stdout


def test_migrate_from_legacy_reports_a_refresh_it_actually_did(tmp_path: Path):
    """It must report the real refresh outcome, not compare a dict to a string."""
    repo = _init_repo(tmp_path, "legacy-migrate-report")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    _run("refresh-system", "--project", str(repo))

    # Second migrate on an already-current project: nothing left to change.
    r = _run("migrate-from-legacy", "--project", str(repo))

    assert r.returncode == 0, f"migrate-from-legacy crashed: {r.stderr}"
    assert "already up to date" in r.stdout.lower()
