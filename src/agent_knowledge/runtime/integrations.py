"""Auto-detect and install tool integrations (Cursor, Claude, Codex)."""

from __future__ import annotations

import shutil
from pathlib import Path

from .paths import get_assets_dir

# Expected Cursor hook events — used by integration health checks.
CURSOR_EXPECTED_HOOK_EVENTS = {"session-start", "post-write", "stop", "preCompact"}

# Expected Cursor command files.
CURSOR_EXPECTED_COMMANDS = {"memory-update.md", "system-update.md", "absorb.md"}

# Expected Claude hook events — used by integration health checks.
CLAUDE_EXPECTED_HOOK_EVENTS = {"SessionStart", "Stop", "PreCompact"}

# Expected Claude command files.
CLAUDE_EXPECTED_COMMANDS = {"memory-update.md", "system-update.md", "absorb.md"}

TOOLS = ("cursor", "claude", "codex")


def detect(repo: Path) -> dict[str, bool]:
    """Return which tools are detected in the repo."""
    return {
        "cursor": (repo / ".cursor").is_dir(),
        "claude": (repo / ".claude").is_dir() or (repo / "CLAUDE.md").is_file(),
        "codex": (repo / ".codex").is_dir(),
    }


def _copy_template(src: Path, dst: Path, replacements: dict[str, str], *, force: bool = False) -> str:
    """Copy a template file with placeholder substitutions. Returns action taken."""
    if dst.exists() and not force:
        return "exists"
    dst.parent.mkdir(parents=True, exist_ok=True)
    content = src.read_text()
    for placeholder, value in replacements.items():
        content = content.replace(placeholder, value)
    dst.write_text(content)
    return "created" if not dst.exists() else "updated"


_CURSOR_RULE = """\
---
description: agent-knowledge -- project memory contract, always active
alwaysApply: true
---

This project uses **agent-knowledge** for persistent memory.
All knowledge lives in `./agent-knowledge/` (symlink to external vault).

## On session start

1. Read `./agent-knowledge/STATUS.md`
2. If `onboarding: pending` — read `AGENTS.md` and perform First-Time Onboarding
3. If `onboarding: complete` — read `./agent-knowledge/Memory/MEMORY.md`
   - Load branch notes relevant to the current task
   - Scan `./agent-knowledge/History/history.md` for recent activity if useful

## Knowledge layers

| Layer | Canonical? | Use for |
|-------|-----------|---------|
| `Memory/` | Yes | Stable project truth — write here |
| `History/` | Yes (diary) | What happened over time |
| `Evidence/` | No | Raw imports — never promote to Memory |
| `Outputs/` | No | Generated views — never treat as truth |
| `Sessions/` | No | Temporary state — prune aggressively |

## After meaningful work

- Write confirmed facts to `./agent-knowledge/Memory/<branch>.md`
- Run `/memory-update` — sync, update branches, summarize what changed

## Periodic (every few sessions)

- Run `/system-update` to refresh integration files to the latest framework version

Keep ontology small and project-native. Do not force generic templates.
"""


def install_cursor(repo: Path, *, dry_run: bool = False, force: bool = False) -> list[str]:
    """Install Cursor hooks and rules integration."""
    assets = get_assets_dir()
    actions = []
    repo_abs = str(repo.resolve())

    # Hooks
    hooks_src = assets / "templates" / "integrations" / "cursor" / "hooks.json"
    hooks_dst = repo / ".cursor" / "hooks.json"
    if hooks_dst.exists() and not force:
        actions.append("  exists: .cursor/hooks.json")
    elif dry_run:
        actions.append("  [dry-run] would create: .cursor/hooks.json")
    else:
        hooks_dst.parent.mkdir(parents=True, exist_ok=True)
        content = hooks_src.read_text().replace("<repo-path>", repo_abs)
        hooks_dst.write_text(content)
        actions.append("  created: .cursor/hooks.json")

    # Rule
    rule_dst = repo / ".cursor" / "rules" / "agent-knowledge.mdc"
    if rule_dst.exists() and not force:
        actions.append("  exists: .cursor/rules/agent-knowledge.mdc")
    elif dry_run:
        actions.append("  [dry-run] would create: .cursor/rules/agent-knowledge.mdc")
    else:
        rule_dst.parent.mkdir(parents=True, exist_ok=True)
        rule_dst.write_text(_CURSOR_RULE)
        actions.append("  created: .cursor/rules/agent-knowledge.mdc")

    # Commands
    commands_template_dir = assets / "templates" / "integrations" / "cursor" / "commands"
    if commands_template_dir.is_dir():
        commands_dst_dir = repo / ".cursor" / "commands"
        for cmd_src in sorted(commands_template_dir.glob("*.md")):
            cmd_dst = commands_dst_dir / cmd_src.name
            rel = f".cursor/commands/{cmd_src.name}"
            if cmd_dst.exists() and not force:
                actions.append(f"  exists: {rel}")
            elif dry_run:
                actions.append(f"  [dry-run] would create: {rel}")
            else:
                commands_dst_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(cmd_src, cmd_dst)
                actions.append(f"  created: {rel}")

    return actions


def install_claude(repo: Path, *, dry_run: bool = False, force: bool = False) -> list[str]:
    """Install Claude project-local integration (settings, commands, instructions)."""
    assets = get_assets_dir()
    actions = []
    repo_abs = str(repo.resolve())

    # Settings (hooks)
    settings_src = assets / "templates" / "integrations" / "claude" / "settings.json"
    settings_dst = repo / ".claude" / "settings.json"
    if settings_dst.exists() and not force:
        actions.append("  exists: .claude/settings.json")
    elif dry_run:
        actions.append("  [dry-run] would create: .claude/settings.json")
    else:
        settings_dst.parent.mkdir(parents=True, exist_ok=True)
        content = settings_src.read_text().replace("<repo-path>", repo_abs)
        settings_dst.write_text(content)
        actions.append("  created: .claude/settings.json")

    # Commands
    commands_template_dir = assets / "templates" / "integrations" / "claude" / "commands"
    if commands_template_dir.is_dir():
        commands_dst_dir = repo / ".claude" / "commands"
        for cmd_src in sorted(commands_template_dir.glob("*.md")):
            cmd_dst = commands_dst_dir / cmd_src.name
            rel = f".claude/commands/{cmd_src.name}"
            if cmd_dst.exists() and not force:
                actions.append(f"  exists: {rel}")
            elif dry_run:
                actions.append(f"  [dry-run] would create: {rel}")
            else:
                commands_dst_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(cmd_src, cmd_dst)
                actions.append(f"  created: {rel}")

    # Project-local CLAUDE.md (runtime contract)
    claude_md_src = assets / "templates" / "integrations" / "claude" / "CLAUDE.md"
    claude_md_dst = repo / ".claude" / "CLAUDE.md"
    if claude_md_dst.exists() and not force:
        actions.append("  exists: .claude/CLAUDE.md")
    elif dry_run:
        actions.append("  [dry-run] would create: .claude/CLAUDE.md")
    else:
        claude_md_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(claude_md_src, claude_md_dst)
        actions.append("  created: .claude/CLAUDE.md")

    return actions


def install_codex(repo: Path, *, dry_run: bool = False, force: bool = False) -> list[str]:
    """Install Codex .codex/AGENTS.md integration."""
    assets = get_assets_dir()
    actions = []

    src = assets / "templates" / "integrations" / "codex" / "AGENTS.md"
    dst = repo / ".codex" / "AGENTS.md"

    if dst.exists() and not force:
        actions.append(f"  exists: .codex/AGENTS.md")
    elif dry_run:
        actions.append(f"  [dry-run] would create: .codex/AGENTS.md")
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        actions.append(f"  created: .codex/AGENTS.md")

    return actions


_INSTALLERS = {
    "cursor": install_cursor,
    "claude": install_claude,
    "codex": install_codex,
}


def install_all(
    repo: Path,
    detected: dict[str, bool],
    *,
    dry_run: bool = False,
    force: bool = False,
) -> dict[str, list[str]]:
    """Install bridge files for detected integrations.

    Cursor and Claude are always installed because their project-local
    integration files (hooks, rules, settings, commands) are inert when
    the respective tool is not in use.

    Codex bridges are only installed when the .codex/ marker directory
    is detected, to avoid polluting repos that don't use it.
    """
    results: dict[str, list[str]] = {}

    # Cursor: always install -- hooks/rules are inert outside Cursor
    results["cursor"] = _INSTALLERS["cursor"](repo, dry_run=dry_run, force=force)

    # Claude: always install -- settings/commands are inert outside Claude
    results["claude"] = _INSTALLERS["claude"](repo, dry_run=dry_run, force=force)

    # Codex: install only when detected
    if detected.get("codex", False):
        results["codex"] = _INSTALLERS["codex"](repo, dry_run=dry_run, force=force)

    return results
