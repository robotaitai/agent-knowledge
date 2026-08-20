"""run_bash_script must not drag Rosetta translation into its children.

An x86_64 Python on Apple Silicon runs under Rosetta, and its children get
the x86_64 slice of universal binaries -- so bash and every tool it forks
run translated at a ~7x penalty (agent-knowledge-3x7: init was 16s of which
~14s was translated fork overhead).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from agent_knowledge.runtime import shell


def _sysctl(name: str) -> str:
    r = subprocess.run(["sysctl", "-n", name], capture_output=True, text=True)
    return r.stdout.strip()


@pytest.mark.skipif(sys.platform != "darwin", reason="Rosetta is macOS-only")
def test_bash_children_run_native_on_apple_silicon(tmp_path: Path, monkeypatch):
    if _sysctl("hw.optional.arm64") != "1":
        pytest.skip("not an Apple Silicon host")
    if subprocess.run(["arch", "-arm64", "bash", "-c", "true"], capture_output=True).returncode != 0:
        pytest.skip("PATH bash has no arm64 slice (migrated Intel install)")

    out = tmp_path / "arch.txt"
    script = tmp_path / "print-arch.sh"
    script.write_text(f'#!/bin/bash\narch > "{out}"\n', encoding="utf-8")

    monkeypatch.setattr(shell, "_bash_prefix", None)
    monkeypatch.setattr(shell, "get_script", lambda name: script)
    rc = shell.run_bash_script("print-arch.sh", [])

    assert rc == 0
    assert out.read_text(encoding="utf-8").strip() == "arm64"


def test_prefix_used_when_python_is_translated(monkeypatch):
    monkeypatch.setattr(shell, "_bash_prefix", None)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(shell, "_proc_translated", lambda: True)
    monkeypatch.setattr(shell, "_native_bash_ok", lambda bash: True)

    assert shell._rosetta_escape_prefix("bash") == ["arch", "-arm64"]


def test_no_prefix_when_python_is_native(monkeypatch):
    monkeypatch.setattr(shell, "_bash_prefix", None)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(shell, "_proc_translated", lambda: False)

    assert shell._rosetta_escape_prefix("bash") == []


def test_no_prefix_when_bash_has_no_native_slice(monkeypatch):
    monkeypatch.setattr(shell, "_bash_prefix", None)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(shell, "_proc_translated", lambda: True)
    monkeypatch.setattr(shell, "_native_bash_ok", lambda bash: False)

    assert shell._rosetta_escape_prefix("bash") == []
