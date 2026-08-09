"""Subprocess wrappers for calling bundled scripts."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from .paths import get_script

# Common Git-for-Windows bash locations, tried in order on Windows.
_WINDOWS_BASH_CANDIDATES = [
    r"C:\Program Files\Git\bin\bash.exe",
    r"C:\Program Files\Git\usr\bin\bash.exe",
    r"C:\Program Files (x86)\Git\bin\bash.exe",
]

_bash_exe: str | None = None


def _find_bash() -> str:
    """Return the bash executable path, raising RuntimeError on Windows if not found."""
    global _bash_exe
    if _bash_exe is not None:
        return _bash_exe

    # Non-Windows: bash must be on PATH.
    if sys.platform != "win32":
        _bash_exe = "bash"
        return _bash_exe

    # Windows: check PATH first (Git Bash, WSL, Cygwin may all put bash there).
    if shutil.which("bash"):
        _bash_exe = "bash"
        return _bash_exe

    # Fall back to known Git-for-Windows install paths.
    for candidate in _WINDOWS_BASH_CANDIDATES:
        if Path(candidate).is_file():
            _bash_exe = candidate
            return _bash_exe

    raise RuntimeError(
        "bash not found. bedrock requires bash to run its scripts.\n"
        "On Windows, install Git for Windows (https://git-scm.com/download/win) "
        "and ensure 'Git Bash' is added to your PATH, then retry."
    )


def run_bash_script(name: str, args: list[str]) -> int:
    """Run a bundled bash script and return its exit code."""
    script = get_script(name)
    try:
        bash = _find_bash()
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    result = subprocess.run([bash, str(script)] + args)
    return result.returncode


def run_python_script(name: str, args: list[str]) -> int:
    """Run a bundled Python script and return its exit code."""
    script = get_script(name)
    result = subprocess.run([sys.executable, str(script)] + args)
    return result.returncode


def has_display() -> bool:
    """Whether a GUI browser can plausibly be opened here.

    A headless box or an SSH session has no browser to open; treating that as a
    normal environment (print the path instead) beats letting the launcher fail
    after the shell prompt has already returned.
    """
    if os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_TTY"):
        return False
    if sys.platform == "darwin" or sys.platform == "win32":
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def open_in_browser(target: str) -> bool:
    """Open a file path or URL in the system browser.

    Returns False when there is no display, so the caller can print the target
    instead. The launcher's own stderr is discarded: it arrives after the shell
    prompt has returned and would otherwise scribble over the next prompt.
    """
    if not has_display():
        return False

    try:
        if sys.platform == "darwin":
            subprocess.run(["open", target], check=False, stderr=subprocess.DEVNULL)
        elif sys.platform == "win32":
            os.startfile(target)  # noqa: S606 -- Windows' own shell-open verb
        else:
            subprocess.run(["xdg-open", target], check=False, stderr=subprocess.DEVNULL)
    except OSError:
        return False
    return True
