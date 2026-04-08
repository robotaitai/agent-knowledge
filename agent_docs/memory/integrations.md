---
area: integrations
updated: 2026-04-08
---

# Integrations

## Purpose
Multi-tool detection and bridge file installation for Cursor, Claude, and Codex.

## Current State

### Detection logic (runtime/integrations.py)
- `detect(repo_path)` returns `{"cursor": bool, "claude": bool, "codex": bool}`.
- Cursor: always True (default integration).
- Claude: True if `.claude/` directory exists in repo.
- Codex: True if `.codex/` directory exists in repo.

### Bridge files installed per tool
- **Cursor**: `.cursor/hooks.json` (post-write hook calling `agent-knowledge update`) + `.cursor/rules/agent-knowledge.mdc` (alwaysApply rule instructing agent to read STATUS.md on session start).
- **Claude**: `CLAUDE.md` at project root (directs Claude to AGENTS.md and STATUS.md).
- **Codex**: `.codex/AGENTS.md` (directs Codex to root AGENTS.md and STATUS.md).

### Onboarding handoff
- Bridge files instruct agents to check `./agent-knowledge/STATUS.md`.
- If `onboarding: pending`, agents should follow `AGENTS.md` first-time onboarding instructions.
- If `onboarding: complete`, agents read `Memory/MEMORY.md` for project context.
- No separate `next-prompt` command needed -- handoff is automatic via repo files.

### init integration
- `init` calls `detect()` then `install_all()` by default.
- `--no-integrations` flag skips auto-detection.
- `--force` flag overwrites existing integration files.
- Existing files are left untouched unless `--force` is passed.

## Decisions

- Cursor rule content (`_CURSOR_RULE`) is inlined as a Python string in `integrations.py` instead of read from a template file. **Why:** pip had a rare bug silently skipping `.mdc` file extraction from wheels during editable installs.
- Cursor is always installed (even without `.cursor/` directory). **Why:** It's the primary tool and the hooks/rule should be present for when Cursor is used.
- Each tool's bridge file is minimal -- it just points to AGENTS.md and STATUS.md. The real instructions live in AGENTS.md to avoid duplication.

## Open Questions

- None currently.
