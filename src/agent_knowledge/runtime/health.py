"""Install health: detect legacy/shadowed installs of this package.

The distribution was renamed over its life (``agent-knowledge`` ->
``agent-knowledge-cli`` -> ``project-bedrock``), but every version ships the
same import package ``agent_knowledge`` and the same ``bedrock`` console script.
When an older distribution is left installed, it can shadow the current one:
``pip`` will not remove a differently-named dist, and ``pipx``/``uv`` will keep
the old venv that owns the ``bedrock`` executable. The result is a machine that
silently runs stale code and never receives updates.

These checks surface that situation with an exact cleanup command so a user is
never stuck on a ghost install without knowing it.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

# Distribution names that predate ``project-bedrock`` and provide the same
# ``agent_knowledge`` import package + ``bedrock`` script.
LEGACY_DIST_NAMES = ("agent-knowledge", "agent-knowledge-cli")
CURRENT_DIST_NAME = "project-bedrock"


def _installed_version(dist_name: str) -> str | None:
    """Return the installed version of a distribution, or None if absent."""
    try:
        from importlib import metadata
    except ImportError:  # pragma: no cover - py<3.8
        return None
    try:
        return metadata.version(dist_name)
    except metadata.PackageNotFoundError:
        return None
    except Exception:
        return None


def find_legacy_installs() -> list[dict[str, str]]:
    """Return installed legacy distributions as ``[{"name", "version"}, ...]``."""
    found: list[dict[str, str]] = []
    for name in LEGACY_DIST_NAMES:
        ver = _installed_version(name)
        if ver is not None:
            found.append({"name": name, "version": ver})
    return found


def _agent_knowledge_locations() -> list[str]:
    """Every importable ``agent_knowledge`` package dir on ``sys.path``.

    More than one means a physical copy is shadowing another install (e.g. a
    stale non-editable dir sitting in front of an editable ``.pth``).
    """
    seen: list[str] = []
    for entry in sys.path:
        if not entry:
            continue
        pkg = Path(entry) / "agent_knowledge" / "__init__.py"
        try:
            if pkg.is_file():
                resolved = str(pkg.parent.resolve())
                if resolved not in seen:
                    seen.append(resolved)
        except OSError:
            continue
    return seen


def detect_install_method() -> str:
    """Best-effort guess of how ``bedrock`` is installed: pipx / uv / pip."""
    exe = shutil.which("bedrock") or sys.executable or ""
    haystack = f"{exe} {sys.prefix} {os.environ.get('PIPX_HOME', '')} {os.environ.get('UV_TOOL_DIR', '')}"
    low = haystack.lower()
    if "pipx" in low:
        return "pipx"
    if os.sep + "uv" + os.sep in low or "/uv/tools/" in low or "uv-tool" in low:
        return "uv"
    return "pip"


def _uninstall_command(method: str, dist_name: str) -> str:
    if method == "pipx":
        return f"pipx uninstall {dist_name}"
    if method == "uv":
        return f"uv tool uninstall {dist_name}"
    return f"{Path(sys.executable).name} -m pip uninstall -y {dist_name}"


def check_install_health() -> list[str]:
    """Return human-readable install problems, each with a fix command.

    Empty list means the install looks clean.
    """
    issues: list[str] = []
    method = detect_install_method()

    for legacy in find_legacy_installs():
        issues.append(
            f"Legacy install present: {legacy['name']} {legacy['version']} "
            f"(superseded by {CURRENT_DIST_NAME}). It can shadow updates so you "
            f"keep running old code. Remove it: {_uninstall_command(method, legacy['name'])}"
        )

    locations = _agent_knowledge_locations()
    if len(locations) > 1:
        running = "unknown"
        try:
            import agent_knowledge

            running = str(Path(agent_knowledge.__file__).parent.resolve())
        except Exception:
            pass
        joined = "\n    ".join(locations)
        issues.append(
            "Multiple 'agent_knowledge' package copies are importable; a stale "
            f"copy may be shadowing the current one (running from: {running}):\n    {joined}\n"
            "  Reinstall cleanly, or delete the stale copy/copies above."
        )

    return issues
