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

# Cached `arch` prefix for bash children; None until first computed.
_bash_prefix: list[str] | None = None


def _proc_translated() -> bool:
    """Whether this Python runs translated under Rosetta 2."""
    try:
        r = subprocess.run(
            ["sysctl", "-n", "sysctl.proc_translated"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.stdout.strip() == "1"


def _native_bash_ok(bash: str) -> bool:
    """Whether bash can be launched natively via `arch -arm64`."""
    try:
        r = subprocess.run(
            ["arch", "-arm64", bash, "-c", "true"],
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0


def _rosetta_escape_prefix(bash: str) -> list[str]:
    """Return ["arch", "-arm64"] when bash children should escape Rosetta.

    A translated (x86_64) Python on Apple Silicon spawns the x86_64 slice of
    universal binaries, so bash and every tool it forks would run translated
    too -- a ~7x penalty on fork-heavy scripts. Launching bash through
    `arch -arm64` puts the whole script back on the native architecture.

    Cached for the first bash seen; fine today because _find_bash() also
    caches, so every caller passes the same executable.
    """
    global _bash_prefix
    if _bash_prefix is not None:
        return _bash_prefix
    _bash_prefix = []
    if sys.platform == "darwin" and _proc_translated() and _native_bash_ok(bash):
        _bash_prefix = ["arch", "-arm64"]
    return _bash_prefix


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
    result = subprocess.run([*_rosetta_escape_prefix(bash), bash, str(script)] + args)
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
