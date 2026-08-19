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


def is_remote_session() -> bool:
    """Whether this shell is an SSH session onto some other machine.

    Callers need this to know whether a local path is worth printing at all: a
    file:// URI handed to a browser on the client resolves against the
    *client's* filesystem, where it does not exist.
    """
    return bool(os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_TTY"))


def has_display() -> bool:
    """Whether a GUI browser can plausibly be opened here.

    A headless box has no browser to open; treating that as a normal
    environment (print the path instead) beats letting the launcher fail after
    the shell prompt has already returned.

    SSH is not headless by definition -- `ssh -X` forwards a real, usable
    display -- so a remote session is judged by DISPLAY like any other. Only
    darwin and win32, where a display is assumed rather than advertised in the
    environment, need the remote case ruled out explicitly: there the launcher
    would open a browser on a console nobody is sitting at.
    """
    if sys.platform == "darwin" or sys.platform == "win32":
        return not is_remote_session()
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def open_in_browser(target: str) -> bool:
    """Open a file path or URL in the system browser.

    Returns False when there is no display, so the caller can print the target
    instead.

    The launcher is spawned and never waited on: on a machine without a GUI
    session `open` can block for a long time, which would stall a caller that
    has more to do -- `bedrock view --serve` still has a port to bind. Its
    output is discarded too, since it arrives after the shell prompt has
    returned and would otherwise scribble over the next prompt.
    """
    if not has_display():
        return False

    browser = os.environ.get("BROWSER")
    if browser:
        argv = [browser, target]
    elif sys.platform == "darwin":
        argv = ["open", target]
    elif sys.platform == "win32":
        try:
            os.startfile(target)  # noqa: S606 -- Windows' own shell-open verb
        except OSError:
            return False
        return True
    else:
        argv = ["xdg-open", target]

    try:
        subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        return False
    return True
