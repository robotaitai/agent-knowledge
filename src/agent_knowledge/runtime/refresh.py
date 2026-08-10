"""Framework refresh for bedrock project integrations.

Refreshes project-level integration files (hooks, bridge files, AGENTS.md,
.agent-project.yaml fields, STATUS.md fields) to match the currently installed
framework version, without touching Memory/, Evidence/, Sessions/, or any
project-curated knowledge.

Idempotent: safe to run multiple times. When everything is already current,
all items report "up-to-date" and no files are written.
"""

from __future__ import annotations

import datetime
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from agent_knowledge import __version__
from agent_knowledge.runtime import migrations as _migrations
from agent_knowledge.runtime.frontmatter import fm_get, fm_set
from agent_knowledge.runtime.paths import get_assets_dir


# --------------------------------------------------------------------------- #
# Utilities                                                                    #
# --------------------------------------------------------------------------- #


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
    except OSError:
        return ""


def _write(path: Path, content: str, *, dry_run: bool) -> str:
    if dry_run:
        return "dry-run"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return "updated"


# Kept as module-private aliases so existing call sites read unchanged.
_fm_get = fm_get
_fm_set = fm_set


def _yaml_set(text: str, key: str, value: str) -> str:
    """Add or update a top-level key in a bare YAML file (no frontmatter delimiters)."""
    pattern = rf"^{re.escape(key)}:.*$"
    quoted = f'"{value}"'
    if re.search(pattern, text, re.MULTILINE):
        return re.sub(pattern, f"{key}: {quoted}", text, flags=re.MULTILINE)
    return text.rstrip("\n") + f"\n{key}: {quoted}\n"


def _normalize_json(text: str) -> dict | None:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


# Hook commands bedrock has ever generated, current and historical
# (agent-knowledge is the pre-rename spelling). A command must match one of
# these *in full* to be replaced: anything a project extended -- for example
# "bedrock sync --project . && npm run notify" -- is its own config and must
# survive a refresh. The argument pattern stops at a shell operator so a chained
# command cannot be swallowed, but allows spaces and quotes inside one argument.
_CLI = r"(?:bedrock|agent-knowledge)"
_ARG = r"""(?:"[^"]*"|'[^']*'|[^&|;<>]+?)"""
# --project is optional: current templates omit it entirely and let the CLI walk
# up to the project root, but every historical form still has to be recognized
# so an old checkout is repaired rather than left alone.
_PROJ = rf"(?: --project {_ARG})?"
_SUMMARY = rf"(?: --summary-file {_ARG})?"
_GENERATED_HOOK_COMMANDS = tuple(
    re.compile(pattern)
    for pattern in (
        rf"{_CLI} sync{_PROJ}",
        rf"{_CLI} sync{_PROJ} && {_CLI} refresh-system{_PROJ}",
        rf"{_CLI} update{_SUMMARY}{_PROJ}",
    )
)


def _is_bedrock_command(command: Any) -> bool:
    if not isinstance(command, str):
        return False
    stripped = command.strip()
    return any(p.fullmatch(stripped) for p in _GENERATED_HOOK_COMMANDS)


def _merge_claude_hooks(template: dict, current: dict) -> dict:
    """Replace bedrock-owned Claude hooks with the template's, keep everything else.

    `.claude/settings.json` is shared with the project (permissions, env, and
    hooks the project added itself), so a refresh may only rewrite the entries
    bedrock generated.
    """
    merged = json.loads(json.dumps(current))
    tmpl_hooks = template.get("hooks") or {}
    curr_hooks = merged.get("hooks")
    if not isinstance(curr_hooks, dict):
        curr_hooks = {}

    for event, tmpl_groups in tmpl_hooks.items():
        kept: list[Any] = []
        for group in curr_hooks.get(event, []) or []:
            if not isinstance(group, dict):
                kept.append(group)
                continue
            inner = [
                h
                for h in (group.get("hooks") or [])
                if not (isinstance(h, dict) and _is_bedrock_command(h.get("command")))
            ]
            if inner:
                kept.append({**group, "hooks": inner})
        curr_hooks[event] = list(tmpl_groups) + kept

    merged["hooks"] = curr_hooks
    return merged


def _merge_cursor_hooks(template: dict, current: dict) -> dict:
    """Replace bedrock-owned Cursor hooks with the template's, keep everything else."""
    merged = json.loads(json.dumps(current))
    if template.get("version") is not None:
        merged["version"] = template["version"]
    if template.get("description"):
        merged["description"] = template["description"]

    kept = [
        h
        for h in (merged.get("hooks") or [])
        if not (isinstance(h, dict) and _is_bedrock_command(h.get("command")))
    ]
    merged["hooks"] = list(template.get("hooks") or []) + kept
    return merged


# --------------------------------------------------------------------------- #
# Per-integration refreshers                                                   #
# --------------------------------------------------------------------------- #


def _refresh_agents_md(repo_root: Path, *, dry_run: bool) -> dict[str, Any]:
    """Refresh the framework header in AGENTS.md while preserving the project section."""
    target = repo_root / "AGENTS.md"
    template_path = get_assets_dir() / "templates" / "project" / "AGENTS.md"

    if not template_path.is_file():
        return {"target": "AGENTS.md", "action": "skip", "detail": "bundled template not found"}

    template = template_path.read_text(encoding="utf-8")
    current = _read_text(target)

    _TODO = "## TODO"
    tmpl_parts = template.split(_TODO, 1)
    tmpl_header = tmpl_parts[0].rstrip("\n")

    if not current:
        action = _write(target, template, dry_run=dry_run)
        return {"target": "AGENTS.md", "action": action, "detail": "created from template"}

    curr_parts = current.split(_TODO, 1)
    curr_header = curr_parts[0].rstrip("\n")
    # Preserve whatever the project has after ## TODO
    curr_tail = (_TODO + curr_parts[1]) if len(curr_parts) > 1 else (
        _TODO + tmpl_parts[1] if len(tmpl_parts) > 1 else ""
    )

    if curr_header.strip() == tmpl_header.strip():
        return {"target": "AGENTS.md", "action": "up-to-date", "detail": "framework header is current"}

    merged = tmpl_header + "\n\n" + curr_tail if curr_tail else tmpl_header
    action = _write(target, merged.rstrip("\n") + "\n", dry_run=dry_run)
    return {"target": "AGENTS.md", "action": action, "detail": "updated framework header, preserved project section"}


def _refresh_cursor_hooks(repo_root: Path, *, dry_run: bool) -> dict[str, Any]:
    """Refresh .cursor/hooks.json from the bundled template (with repo-path substitution)."""
    target = repo_root / ".cursor" / "hooks.json"
    template_path = get_assets_dir() / "templates" / "integrations" / "cursor" / "hooks.json"

    if not template_path.is_file():
        return {"target": ".cursor/hooks.json", "action": "skip", "detail": "bundled template not found"}

    if not target.is_file():
        return {"target": ".cursor/hooks.json", "action": "skip", "detail": "not installed; run: bedrock init"}

    tmpl_obj = _normalize_json(template_path.read_text(encoding="utf-8"))
    curr_obj = _normalize_json(target.read_text(encoding="utf-8", errors="replace"))

    if tmpl_obj is None or curr_obj is None:
        return {"target": ".cursor/hooks.json", "action": "skip", "detail": "could not parse JSON"}

    merged = _merge_cursor_hooks(tmpl_obj, curr_obj)
    if merged == curr_obj:
        return {"target": ".cursor/hooks.json", "action": "up-to-date", "detail": "hooks match current template"}

    action = _write(target, json.dumps(merged, indent=2) + "\n", dry_run=dry_run)
    return {"target": ".cursor/hooks.json", "action": action, "detail": "refreshed from bundled template"}


def _refresh_cursor_rule(repo_root: Path, *, dry_run: bool) -> dict[str, Any]:
    """Refresh .cursor/rules/bedrock.mdc, migrating from agent-knowledge.mdc if needed."""
    target = repo_root / ".cursor" / "rules" / "bedrock.mdc"
    legacy = repo_root / ".cursor" / "rules" / "agent-knowledge.mdc"
    template_path = get_assets_dir() / "templates" / "integrations" / "cursor" / "bedrock.mdc"

    if template_path.is_file():
        template = template_path.read_text(encoding="utf-8")
    else:
        from agent_knowledge.runtime.integrations import _CURSOR_RULE as _fallback
        template = _fallback

    # Migrate legacy filename to bedrock.mdc
    if legacy.is_file() and not target.is_file():
        if dry_run:
            return {"target": ".cursor/rules/bedrock.mdc", "action": "dry-run", "detail": "would rename agent-knowledge.mdc -> bedrock.mdc"}
        legacy.rename(target)
        action = _write(target, template, dry_run=False)
        return {"target": ".cursor/rules/bedrock.mdc", "action": action, "detail": "renamed from agent-knowledge.mdc and refreshed"}

    if not target.is_file():
        return {"target": ".cursor/rules/bedrock.mdc", "action": "skip", "detail": "not installed; run: bedrock init"}

    current = target.read_text(encoding="utf-8", errors="replace")
    if current.strip() == template.strip():
        return {"target": ".cursor/rules/bedrock.mdc", "action": "up-to-date", "detail": "rule is current"}

    action = _write(target, template, dry_run=dry_run)
    return {"target": ".cursor/rules/bedrock.mdc", "action": action, "detail": "refreshed from bundled template"}


def _refresh_claude_settings(repo_root: Path, *, dry_run: bool) -> dict[str, Any]:
    """Refresh .claude/settings.json from the bundled template (with repo-path substitution)."""
    target = repo_root / ".claude" / "settings.json"
    template_path = get_assets_dir() / "templates" / "integrations" / "claude" / "settings.json"

    if not template_path.is_file():
        return {"target": ".claude/settings.json", "action": "skip", "detail": "bundled template not found"}

    if not target.is_file():
        return {"target": ".claude/settings.json", "action": "skip", "detail": "not installed; run: bedrock init"}

    tmpl_obj = _normalize_json(template_path.read_text(encoding="utf-8"))
    curr_obj = _normalize_json(target.read_text(encoding="utf-8", errors="replace"))

    if tmpl_obj is None or curr_obj is None:
        return {"target": ".claude/settings.json", "action": "skip", "detail": "could not parse JSON"}

    merged = _merge_claude_hooks(tmpl_obj, curr_obj)
    if merged == curr_obj:
        return {"target": ".claude/settings.json", "action": "up-to-date", "detail": "settings match current template"}

    action = _write(target, json.dumps(merged, indent=2) + "\n", dry_run=dry_run)
    return {"target": ".claude/settings.json", "action": action, "detail": "refreshed bedrock hooks, preserved project settings"}


def _refresh_claude_md(repo_root: Path, *, dry_run: bool) -> dict[str, Any]:
    """Refresh .claude/CLAUDE.md if it matches the bundled template; warn if customized."""
    target = repo_root / ".claude" / "CLAUDE.md"
    template_path = get_assets_dir() / "templates" / "integrations" / "claude" / "CLAUDE.md"

    if not template_path.is_file():
        return {"target": ".claude/CLAUDE.md", "action": "skip", "detail": "bundled template not found"}

    if not target.is_file():
        return {"target": ".claude/CLAUDE.md", "action": "skip", "detail": "not installed; run: bedrock init"}

    template = template_path.read_text(encoding="utf-8")
    current = target.read_text(encoding="utf-8", errors="replace")

    if current.strip() == template.strip():
        return {"target": ".claude/CLAUDE.md", "action": "up-to-date", "detail": "already matches template"}

    # Any file whose first non-empty line is a known bedrock header was installed by us.
    first_line = current.strip().splitlines()[0].strip() if current.strip() else ""
    _KNOWN_HEADERS = {"# bedrock", "# agent-knowledge"}
    if first_line not in _KNOWN_HEADERS:
        return {
            "target": ".claude/CLAUDE.md",
            "action": "warn",
            "detail": "first line is not a known bedrock header — appears manually customized; skipping",
        }

    action = _write(target, template, dry_run=dry_run)
    return {"target": ".claude/CLAUDE.md", "action": action, "detail": "refreshed from bundled template"}


def _refresh_claude_commands(repo_root: Path, *, dry_run: bool) -> list[dict[str, Any]]:
    """Refresh .claude/commands/ from the bundled templates."""
    commands_dir = repo_root / ".claude" / "commands"
    template_dir = get_assets_dir() / "templates" / "integrations" / "claude" / "commands"
    results: list[dict[str, Any]] = []

    if not template_dir.is_dir():
        return [{"target": ".claude/commands/", "action": "skip", "detail": "no bundled command templates"}]

    for template_file in sorted(template_dir.glob("*.md")):
        rel = f".claude/commands/{template_file.name}"
        target = commands_dir / template_file.name

        if not target.exists():
            action = _write(target, template_file.read_text(encoding="utf-8"), dry_run=dry_run)
            results.append({"target": rel, "action": action, "detail": "created from bundled template"})
            continue

        template_content = template_file.read_text(encoding="utf-8")
        current_content = target.read_text(encoding="utf-8", errors="replace")

        if current_content.strip() == template_content.strip():
            results.append({"target": rel, "action": "up-to-date", "detail": "command is current"})
            continue

        action = _write(target, template_content, dry_run=dry_run)
        results.append({"target": rel, "action": action, "detail": "refreshed from bundled template"})

    return results


def _refresh_cursor_commands(repo_root: Path, *, dry_run: bool) -> list[dict[str, Any]]:
    """Refresh .cursor/commands/ from the bundled templates."""
    commands_dir = repo_root / ".cursor" / "commands"
    template_dir = get_assets_dir() / "templates" / "integrations" / "cursor" / "commands"
    results: list[dict[str, Any]] = []

    if not template_dir.is_dir():
        return [{"target": ".cursor/commands/", "action": "skip", "detail": "no bundled command templates"}]

    for template_file in sorted(template_dir.glob("*.md")):
        rel = f".cursor/commands/{template_file.name}"
        target = commands_dir / template_file.name

        if not target.exists():
            action = _write(target, template_file.read_text(encoding="utf-8"), dry_run=dry_run)
            results.append({"target": rel, "action": action, "detail": "created from bundled template"})
            continue

        template_content = template_file.read_text(encoding="utf-8")
        current_content = target.read_text(encoding="utf-8", errors="replace")

        if current_content.strip() == template_content.strip():
            results.append({"target": rel, "action": "up-to-date", "detail": "command is current"})
            continue

        action = _write(target, template_content, dry_run=dry_run)
        results.append({"target": rel, "action": action, "detail": "refreshed from bundled template"})

    return results


def _refresh_codex_agents_md(repo_root: Path, *, dry_run: bool) -> dict[str, Any]:
    """Refresh .codex/AGENTS.md from the bundled template."""
    target = repo_root / ".codex" / "AGENTS.md"
    template_path = get_assets_dir() / "templates" / "integrations" / "codex" / "AGENTS.md"

    if not template_path.is_file():
        return {"target": ".codex/AGENTS.md", "action": "skip", "detail": "bundled template not found"}

    if not target.is_file():
        return {"target": ".codex/AGENTS.md", "action": "skip", "detail": "not installed; run: bedrock init"}

    template = template_path.read_text(encoding="utf-8")
    current = target.read_text(encoding="utf-8", errors="replace")

    if current.strip() == template.strip():
        return {"target": ".codex/AGENTS.md", "action": "up-to-date", "detail": "already matches template"}

    action = _write(target, template, dry_run=dry_run)
    return {"target": ".codex/AGENTS.md", "action": action, "detail": "refreshed from bundled template"}


def _refresh_gemini_md(repo_root: Path, *, dry_run: bool) -> dict[str, Any]:
    """Refresh GEMINI.md from the bundled template (Gemini CLI / Antigravity)."""
    target = repo_root / "GEMINI.md"
    template_path = get_assets_dir() / "templates" / "integrations" / "gemini" / "GEMINI.md"

    if not template_path.is_file():
        return {"target": "GEMINI.md", "action": "skip", "detail": "bundled template not found"}

    if not target.is_file():
        return {"target": "GEMINI.md", "action": "skip", "detail": "not installed; run: bedrock init"}

    template = template_path.read_text(encoding="utf-8")
    current = target.read_text(encoding="utf-8", errors="replace")

    if current.strip() == template.strip():
        return {"target": "GEMINI.md", "action": "up-to-date", "detail": "already matches template"}

    action = _write(target, template, dry_run=dry_run)
    return {"target": "GEMINI.md", "action": action, "detail": "refreshed from bundled template"}


def _refresh_status_md(vault_dir: Path, version: str, *, dry_run: bool) -> dict[str, Any]:
    """Update framework_version and last_system_refresh in STATUS.md frontmatter.

    last_system_refresh is only written when the framework_version is actually
    changing, to preserve idempotency on repeated runs.
    """
    target = vault_dir / "STATUS.md"

    if not target.is_file():
        return {"target": "STATUS.md", "action": "skip", "detail": "file not found"}

    current = target.read_text(encoding="utf-8", errors="replace")
    prior = _fm_get(current, "framework_version")

    # If version is already set correctly, this is a no-op
    if prior == version:
        return {"target": "STATUS.md", "action": "up-to-date", "detail": f"framework_version already {version}"}

    # Version is changing (or absent) — update both fields
    updated = _fm_set(current, "framework_version", version)
    updated = _fm_set(updated, "last_system_refresh", _now_iso())

    action = _write(target, updated, dry_run=dry_run)
    detail = f"set framework_version: {version}"
    if prior:
        detail += f" (was: {prior})"
    return {"target": "STATUS.md", "action": action, "detail": detail}


def _localize_real_path(text: str) -> tuple[str, bool]:
    """Rewrite an absolute `real_path` to `./bedrock` for local vaults.

    In `vault_mode: local` the vault is always `<repo>/bedrock`, so an absolute
    path only records which machine generated the file and breaks every other
    clone. The rest of the file is already relative.
    """
    if not re.search(r"""^\s*vault_mode:\s*["']?local["']?\s*$""", text, re.MULTILINE):
        return text, False
    # Match the whole line, not a \S+ token: the paths this exists to fix are
    # exactly the ones that may contain spaces or quotes.
    m = re.search(r"^(\s*real_path:)[ \t]*(.*)$", text, re.MULTILINE)
    if not m:
        return text, False
    value = m.group(2).strip().strip("\"'")
    if not value or value.startswith((".", "$", "<")):
        return text, False
    return text[: m.start()] + f"{m.group(1)} ./bedrock" + text[m.end():], True


def _refresh_project_yaml(repo_root: Path, version: str, *, dry_run: bool) -> dict[str, Any]:
    """Update framework_version and de-absolutize real_path in .agent-project.yaml."""
    target = repo_root / ".agent-project.yaml"

    if not target.is_file():
        return {"target": ".agent-project.yaml", "action": "skip", "detail": "file not found"}

    current = target.read_text(encoding="utf-8", errors="replace")
    prior = ""
    m = re.search(r'^framework_version:\s*(.+)$', current, re.MULTILINE)
    if m:
        prior = m.group(1).strip().strip("\"'")

    # Unconditional, not a migration: an older CLI on another machine can
    # reintroduce an absolute path at any time, so this must re-run every refresh.
    updated, localized = _localize_real_path(current)

    if prior == version and not localized:
        return {"target": ".agent-project.yaml", "action": "up-to-date", "detail": f"framework_version already {version}"}

    if prior != version:
        updated = _yaml_set(updated, "framework_version", version)

    action = _write(target, updated, dry_run=dry_run)
    details = []
    if prior != version:
        details.append(f"set framework_version: {version}" + (f" (was: {prior})" if prior else ""))
    if localized:
        details.append("real_path -> ./bedrock (portable across machines)")
    return {"target": ".agent-project.yaml", "action": action, "detail": "; ".join(details)}


def _refresh_gitignore(repo_root: Path, *, dry_run: bool) -> dict[str, Any]:
    """Add bedrock-owned .gitignore patterns the project is missing.

    `connect` wrote the patterns known at the time. refresh-system runs every
    session, so it is where an existing checkout picks up patterns added since.
    """
    from agent_knowledge.runtime.gitignore import ensure_patterns

    if not (repo_root / ".gitignore").is_file():
        return {"target": ".gitignore", "action": "skip", "detail": "no .gitignore in this repo"}

    missing = ensure_patterns(repo_root, dry_run=dry_run)
    if not missing:
        return {"target": ".gitignore", "action": "up-to-date", "detail": "all bedrock patterns present"}

    action = "dry-run" if dry_run else "updated"
    return {"target": ".gitignore", "action": action, "detail": f"added {', '.join(missing)}"}


# --------------------------------------------------------------------------- #
# Staleness check (used by doctor integration)                                 #
# --------------------------------------------------------------------------- #


def is_stale(repo_root: Path) -> tuple[bool, str | None, str]:
    """Check whether the project integration is outdated.

    Returns (stale, prior_version, current_version).
    `stale` is True when the project was last refreshed with an older version.
    """
    vault_dir = repo_root / "bedrock"
    if not vault_dir.is_dir():
        return False, None, __version__

    status_text = _read_text(vault_dir / "STATUS.md")
    prior = _fm_get(status_text, "framework_version")

    if not prior:
        # No version marker at all — legacy project, treat as stale
        return True, None, __version__

    return prior != __version__, prior, __version__


# --------------------------------------------------------------------------- #
# Durable-branch note staleness check (used by doctor)                        #
# --------------------------------------------------------------------------- #

# Maps each memory note area to the source paths most likely to change when
# the note's content becomes stale.
_NOTE_AREA_PATHS: dict[str, list[str]] = {
    "cli":           ["src/agent_knowledge/cli.py"],
    "architecture":  ["src/agent_knowledge/runtime/"],
    "stack":         ["pyproject.toml"],
    "packaging":     ["pyproject.toml", "src/agent_knowledge/__init__.py"],
    "testing":       ["tests/"],
    "deployments":   [".github/workflows/", "pyproject.toml"],
    "conventions":   ["src/agent_knowledge/"],
    "integrations":  ["src/agent_knowledge/runtime/integrations.py",
                      "src/agent_knowledge/runtime/refresh.py"],
    "gotchas":       ["src/agent_knowledge/"],
    "history-layer": ["src/agent_knowledge/runtime/history.py"],
}


def _git_latest_commit_date(repo_root: Path, paths: list[str]) -> str | None:
    """Return ISO date of the most recent commit touching any of the given paths.

    Returns None if git is unavailable or the repo has no commits.
    """
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%cs", "--"] + paths,
            cwd=repo_root,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
        date_str = result.stdout.strip()
        return date_str if date_str else None
    except Exception:
        return None


def check_stale_notes(repo_root: Path) -> list[dict[str, str]]:
    """Check durable-branch Memory notes for potential staleness.

    For each note that declares an `area`, compares the note's `updated` date
    against the most recent git commit touching that area's source paths. If
    source files were modified after the note was last updated, the note is
    flagged as potentially stale.

    Returns a list of warning dicts with keys: path, area, note_updated,
    last_src_commit, update_when.
    """
    vault_dir = repo_root / "bedrock" / "Memory"
    if not vault_dir.is_dir():
        return []

    warnings: list[dict[str, str]] = []

    for md_file in sorted(vault_dir.glob("*.md")):
        text = _read_text(md_file)
        if not text.startswith("---"):
            continue
        note_type = _fm_get(text, "note_type")
        if note_type != "durable-branch":
            continue

        area = _fm_get(text, "area")
        note_updated = _fm_get(text, "updated")
        update_when = _fm_get(text, "update_when")
        if not area or not note_updated:
            continue

        watched_paths = _NOTE_AREA_PATHS.get(area)
        if not watched_paths:
            continue

        last_src = _git_latest_commit_date(repo_root, watched_paths)
        if not last_src:
            continue

        if last_src > note_updated:
            warnings.append({
                "path": str(md_file.relative_to(repo_root / "bedrock")),
                "area": area,
                "note_updated": note_updated,
                "last_src_commit": last_src,
                "update_when": update_when,
            })

    return warnings


# --------------------------------------------------------------------------- #
# Integration health check (used by doctor)                                   #
# --------------------------------------------------------------------------- #


def check_cursor_integration(repo_root: Path) -> dict[str, Any]:
    """Check Cursor integration completeness.

    Returns a dict with 'healthy' bool, 'issues' list, and 'info' detail dict.
    """
    from agent_knowledge.runtime.integrations import (
        CURSOR_EXPECTED_COMMANDS,
        CURSOR_EXPECTED_HOOK_EVENTS,
    )

    issues: list[str] = []
    info: dict[str, Any] = {}

    # Rule
    rule = repo_root / ".cursor" / "rules" / "bedrock.mdc"
    info["rule_installed"] = rule.is_file()
    if not rule.is_file():
        issues.append("Missing .cursor/rules/bedrock.mdc -- run: bedrock refresh-system")

    # Hooks
    hooks_file = repo_root / ".cursor" / "hooks.json"
    info["hooks_installed"] = hooks_file.is_file()
    if hooks_file.is_file():
        try:
            hooks_data = json.loads(hooks_file.read_text(encoding="utf-8"))
            events = {h.get("event") for h in hooks_data.get("hooks", [])}
            missing_events = CURSOR_EXPECTED_HOOK_EVENTS - events
            info["hook_events"] = sorted(events - {None})
            info["missing_hook_events"] = sorted(missing_events)
            if missing_events:
                issues.append(
                    f"Hooks missing events: {', '.join(sorted(missing_events))} "
                    f"-- run: bedrock refresh-system"
                )
        except (json.JSONDecodeError, ValueError):
            issues.append("Invalid .cursor/hooks.json -- run: bedrock refresh-system")
            info["hook_events"] = []
            info["missing_hook_events"] = sorted(CURSOR_EXPECTED_HOOK_EVENTS)
    else:
        issues.append("Missing .cursor/hooks.json -- run: bedrock init")
        info["hook_events"] = []
        info["missing_hook_events"] = sorted(CURSOR_EXPECTED_HOOK_EVENTS)

    # Commands
    commands_dir = repo_root / ".cursor" / "commands"
    installed_commands = [f for f in CURSOR_EXPECTED_COMMANDS if (commands_dir / f).is_file()]
    missing_commands = [f for f in sorted(CURSOR_EXPECTED_COMMANDS) if f not in installed_commands]
    info["commands_installed"] = sorted(installed_commands)
    info["commands_missing"] = missing_commands
    if missing_commands:
        issues.append(
            f"Missing Cursor commands: {', '.join(missing_commands)} "
            f"-- run: bedrock refresh-system"
        )

    return {
        "integration": "cursor",
        "info": info,
        "issues": issues,
        "healthy": len(issues) == 0,
    }


def check_claude_integration(repo_root: Path) -> dict[str, Any]:
    """Check Claude integration completeness.

    Returns a dict with 'healthy' bool, 'issues' list, and 'info' detail dict.
    """
    from agent_knowledge.runtime.integrations import (
        CLAUDE_EXPECTED_COMMANDS,
        CLAUDE_EXPECTED_HOOK_EVENTS,
    )

    issues: list[str] = []
    info: dict[str, Any] = {}

    # CLAUDE.md (runtime contract)
    claude_md = repo_root / ".claude" / "CLAUDE.md"
    info["claude_md_installed"] = claude_md.is_file()
    if not claude_md.is_file():
        issues.append("Missing .claude/CLAUDE.md -- run: bedrock refresh-system")

    # Settings (hooks)
    settings_file = repo_root / ".claude" / "settings.json"
    info["settings_installed"] = settings_file.is_file()
    if settings_file.is_file():
        try:
            settings_data = json.loads(settings_file.read_text(encoding="utf-8"))
            hooks_section = settings_data.get("hooks", {})
            events = set(hooks_section.keys())
            missing_events = CLAUDE_EXPECTED_HOOK_EVENTS - events
            info["hook_events"] = sorted(events)
            info["missing_hook_events"] = sorted(missing_events)
            if missing_events:
                issues.append(
                    f"Settings missing hook events: {', '.join(sorted(missing_events))} "
                    f"-- run: bedrock refresh-system"
                )
        except (json.JSONDecodeError, ValueError):
            issues.append("Invalid .claude/settings.json -- run: bedrock refresh-system")
            info["hook_events"] = []
            info["missing_hook_events"] = sorted(CLAUDE_EXPECTED_HOOK_EVENTS)
    else:
        issues.append("Missing .claude/settings.json -- run: bedrock init")
        info["hook_events"] = []
        info["missing_hook_events"] = sorted(CLAUDE_EXPECTED_HOOK_EVENTS)

    # Commands
    commands_dir = repo_root / ".claude" / "commands"
    installed_commands = [f for f in CLAUDE_EXPECTED_COMMANDS if (commands_dir / f).is_file()]
    missing_commands = [f for f in sorted(CLAUDE_EXPECTED_COMMANDS) if f not in installed_commands]
    info["commands_installed"] = sorted(installed_commands)
    info["commands_missing"] = missing_commands
    if missing_commands:
        issues.append(
            f"Missing Claude commands: {', '.join(missing_commands)} "
            f"-- run: bedrock refresh-system"
        )

    return {
        "integration": "claude",
        "info": info,
        "issues": issues,
        "healthy": len(issues) == 0,
    }


# --------------------------------------------------------------------------- #
# Main entry point                                                             #
# --------------------------------------------------------------------------- #


def run_refresh(
    repo_root: Path,
    *,
    dry_run: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """Refresh the project integration layer to the current framework version.

    Touches only integration bridge files and metadata fields.
    Never reads or writes Memory/, Evidence/, Sessions/, or Outputs/ content.

    Returns a summary dict with action, changes, warnings, and version info.
    """
    from agent_knowledge.runtime.integrations import detect

    version = __version__
    vault_dir = repo_root / "bedrock"
    detected = detect(repo_root)

    # Snapshot prior version before any writes
    status_text = _read_text(vault_dir / "STATUS.md")
    prior_version = _fm_get(status_text, "framework_version") or None

    project_layout = _migrations.read_layout_version(repo_root)

    changes: list[dict[str, Any]] = []
    warnings: list[str] = []

    if project_layout > _migrations.LAYOUT_VERSION:
        # Write nothing: an older CLI would revert a newer project's layout, and
        # this runs from SessionStart, so it would happen on every session.
        warnings.append(
            f"This project uses bedrock layout {project_layout}; this install understands "
            f"{_migrations.LAYOUT_VERSION}. Run: pip install -U project-bedrock"
        )
        return {
            "action": "blocked",
            "framework_version": version,
            "prior_version": prior_version,
            "layout_version": _migrations.LAYOUT_VERSION,
            "project_layout_version": project_layout,
            "dry_run": dry_run,
            "integrations_detected": [k for k, v in detected.items() if v],
            "changes": [],
            "warnings": warnings,
        }

    try:
        run = _migrations.run_migrations(repo_root, dry_run=dry_run)
    except Exception as exc:
        # The chain stopped and left the version unstamped, so it replays next
        # session. Templates do not depend on the layout, so the refresh goes on.
        # The type is kept because a broken session is this failure's only surface,
        # and `str(exc)` alone renders KeyError("Memory") as 'Memory'.
        detail = f"{type(exc).__name__}: {exc}"
        warnings.append(f"Layout migration failed: {detail}")
        changes.append({"target": "layout migration", "action": "failed", "detail": detail})
    else:
        for applied in run.applied:
            changes.append({
                "target": "layout migration",
                "action": "dry-run" if dry_run else "updated",
                "detail": f"{applied.version}: {applied.name}",
            })
        if not run.stamped:
            warnings.append(
                "Could not record layout_version in bedrock/STATUS.md; "
                "these migrations will replay next session."
            )

    # AGENTS.md — the primary agent contract file
    r = _refresh_agents_md(repo_root, dry_run=dry_run)
    changes.append(r)
    if r["action"] == "warn":
        warnings.append(f"AGENTS.md: {r['detail']}")

    # Cursor integration (always installed)
    r = _refresh_cursor_hooks(repo_root, dry_run=dry_run)
    changes.append(r)

    r = _refresh_cursor_rule(repo_root, dry_run=dry_run)
    changes.append(r)

    for r in _refresh_cursor_commands(repo_root, dry_run=dry_run):
        changes.append(r)

    # Claude integration (always installed)
    r = _refresh_claude_settings(repo_root, dry_run=dry_run)
    changes.append(r)

    r = _refresh_claude_md(repo_root, dry_run=dry_run)
    changes.append(r)
    if r["action"] == "warn":
        warnings.append(f".claude/CLAUDE.md: {r['detail']}")

    for r in _refresh_claude_commands(repo_root, dry_run=dry_run):
        changes.append(r)

    # Codex integration (if detected)
    if detected.get("codex"):
        r = _refresh_codex_agents_md(repo_root, dry_run=dry_run)
        changes.append(r)

    # Gemini CLI / Antigravity integration (if detected)
    if detected.get("gemini"):
        r = _refresh_gemini_md(repo_root, dry_run=dry_run)
        changes.append(r)

    # STATUS.md — version markers
    if vault_dir.is_dir():
        r = _refresh_status_md(vault_dir, version, dry_run=dry_run)
        changes.append(r)

    # .agent-project.yaml — version field
    r = _refresh_project_yaml(repo_root, version, dry_run=dry_run)
    changes.append(r)

    # .gitignore — pick up per-machine patterns an older connect never wrote
    changes.append(_refresh_gitignore(repo_root, dry_run=dry_run))

    # Regenerate the HTML site if one already exists (picks up new templates/styles)
    site_html = vault_dir / "Views" / "site" / "index.html"
    if not site_html.exists():
        site_html = vault_dir / "Outputs" / "site" / "index.html"  # legacy path
    if site_html.exists() and not dry_run:
        try:
            from agent_knowledge.runtime.site import generate_site
            generate_site(vault_dir)
            changes.append({"target": "bedrock/Views/site/", "action": "refreshed", "detail": "site regenerated with current templates"})
        except Exception:
            pass

    # Determine overall action
    active_actions = {c["action"] for c in changes}
    if "failed" in active_actions:
        # Ahead of the dry-run branch: a failure is the headline either way, and
        # "refreshed" would claim success for a run where something broke.
        action = "degraded"
    elif dry_run:
        action = "dry-run"
    elif active_actions <= {"up-to-date", "skip", "warn"}:
        action = "up-to-date"
    else:
        action = "refreshed"

    return {
        "action": action,
        "framework_version": version,
        "prior_version": prior_version,
        "layout_version": _migrations.LAYOUT_VERSION,
        # Re-read rather than assume the target: under --dry-run, or after the
        # migration chain raised, the stamp never landed and reporting the target
        # would tell doctor a project is migrated when it is not.
        "project_layout_version": _migrations.read_layout_version(repo_root),
        "dry_run": dry_run,
        "integrations_detected": [k for k, v in detected.items() if v],
        "changes": changes,
        "warnings": warnings,
    }
