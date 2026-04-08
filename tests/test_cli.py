"""Verify CLI commands, help output, JSON mode, and dry-run behavior."""

from __future__ import annotations

import json
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
    r = _run("--version")
    assert r.returncode == 0
    assert "0.1.1" in r.stdout


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


def test_init_installs_claude_bridge_when_detected(tmp_path: Path):
    repo = _init_repo(tmp_path, "claude-test")
    (repo / ".claude").mkdir()
    kh = tmp_path / "kh"
    r = _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    assert r.returncode == 0, f"init failed: {r.stderr}"
    assert (repo / "CLAUDE.md").is_file()
    content = (repo / "CLAUDE.md").read_text()
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
    (repo / ".claude").mkdir()
    (repo / ".codex").mkdir()
    kh = tmp_path / "kh"
    r = _run("init", "--repo", str(repo), "--knowledge-home", str(kh))
    assert r.returncode == 0, f"init failed: {r.stderr}"
    assert (repo / ".cursor" / "hooks.json").is_file()
    assert (repo / "CLAUDE.md").is_file()
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
