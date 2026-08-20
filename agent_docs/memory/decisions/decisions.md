---
note_type: decisions-index
updated: 2026-05-06
tags:
  - agent-knowledge
  - memory
  - decision
---

# 📋 Decision Log

Architectural and process decisions for agent-knowledge.

## ⚙️ 001 - Hatchling as build backend {#001}

- **Date**: 2026-04-08
- **Context**: Needed a modern `pyproject.toml`-only backend that supports `force-include` for non-Python assets
- **Decision**: [[packaging|hatchling]] -- simpler than setuptools, native `force-include`
- **Status**: Active

## 🐚 002 - Keep shell scripts, wrap in Python {#002}

- **Date**: 2026-04-08
- **Context**: Existing bash scripts handle complex file ops. Rewriting all in Python is high risk.
- **Decision**: Keep scripts in `assets/scripts/`, invoke via [[cli|subprocess from click CLI]]
- **Status**: Active

## 🗄️ 003 - External knowledge vault + local symlink {#003}

- **Date**: 2026-04-08
- **Context**: Project knowledge needs to be shareable across tools and openable in Obsidian
- **Decision**: Real knowledge at `~/agent-os/projects/<slug>/`, project repo gets `./agent-knowledge` symlink
- **Status**: Active

## 🚀 004 - Zero-arg init with auto-detection {#004}

- **Date**: 2026-04-08
- **Context**: Reduce friction for new project setup
- **Decision**: [[cli#init (zero-arg)|init]] infers slug from dir name, auto-detects [[integrations|Cursor/Claude/Codex]]
- **Status**: Active

## 🤖 005 - Automatic onboarding via AGENTS.md + STATUS.md {#005}

- **Date**: 2026-04-08
- **Context**: Agents should start maintaining knowledge without extra user commands
- **Decision**: [[STATUS]] tracks onboarding state, `AGENTS.md` instructs agents, [[integrations|bridge files]] reinforce
- **Status**: Active

## 📦 006 - Inline Cursor rule content in Python {#006}

- **Date**: 2026-04-08
- **Context**: pip had a rare bug extracting `.mdc` files from wheels during editable installs
- **Decision**: Inline rule content as a Python string in `integrations.py` (see [[gotchas]])
- **Status**: Active (workaround)

## 🔌 007 - Project-local Cursor integration as primary runtime {#007}

- **Date**: 2026-04-12
- **Context**: Global home-dir hook setup was fragile; agents forgot memory layer between sessions
- **Decision**: `init` installs `.cursor/rules/`, `.cursor/hooks.json`, `.cursor/commands/` per-project; project carries the contract
- **Status**: Active

## 🪝 008 - Full session lifecycle hooks {#008}

- **Date**: 2026-04-12
- **Context**: Only `post-write` and `session-start` hooks existed; stop and compaction events missed
- **Decision**: Add `stop` + `preCompact` hooks both calling `bedrock sync`; hooks stay thin
- **Status**: Active

## 💬 009 - init auto-runs import and shows single clean prompt {#009}

- **Date**: 2026-04-13
- **Context**: `init` output had multiple "Next steps" blocks confusing users
- **Decision**: `init` auto-runs `import-agent-history.sh` and `backfill-history`; shows one agent-chat box at the end
- **Status**: Active

## 🏆 010 - Claude Code as always-installed first-class integration {#010}

- **Date**: 2026-04-13
- **Context**: Claude Code adoption growing; was previously optional/detected-only
- **Decision**: `init` always installs `.claude/` integration (settings.json, CLAUDE.md, commands/); `refresh-system` keeps it current
- **Status**: Active

## 🪨 011 - Rename vault folder to `bedrock/` {#011}

- **Date**: 2026-04-29
- **Context**: Folder was named `agent-knowledge/` which was tied to the old package name. Confusing after CLI rename to `bedrock`.
- **Decision**: Rename vault folder `agent-knowledge/` → `bedrock/` everywhere (v0.4.0). `migrate-vault` command added for existing users. All bridge files, templates, and path references updated.
- **Status**: Active

## 🧜 012 - Mermaid diagrams in site viewer {#012}

- **Date**: 2026-05-04
- **Context**: Memory notes use Mermaid for flowcharts (e.g. onboarding flow in integrations.md). The static HTML site rendered them as raw code blocks.
- **Decision**: Load `mermaid.min.js` in the site viewer and render diagram blocks automatically. SPA retry-on-load pattern used to handle Mermaid initialization timing.
- **Status**: Active

## ✨ 013 - Gemini CLI + Antigravity as first-class integrations {#013}

- **Date**: 2026-05-05
- **Context**: Users asked about Gemini CLI and Google Antigravity IDE. Both use `GEMINI.md` for agent context (Antigravity also reads `AGENTS.md`). Both share `~/.gemini/GEMINI.md` as global config.
- **Decision**: Add `GEMINI.md` template and detection (`.gemini/` dir or `GEMINI.md` present). Wire into `init`, `refresh-system`, and `install-global`. One template covers both tools since they share the same config path.
- **Status**: Active

## 🌐 014 - `install-global` for zero-config global activation {#014}

- **Date**: 2026-05-05
- **Context**: Users without per-project bedrock setup had no way to get memory context automatically. Each tool has a user-global config dir that all projects inherit.
- **Decision**: Add `bedrock install-global` that writes conditional rules to `~/.cursor/rules/`, `~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`, `~/.gemini/GEMINI.md`. Rules are sentinel-guarded (idempotent) and activate only when `./bedrock/STATUS.md` exists in the project.
- **Status**: Active

## 📝 015 - Emoji headers in Memory branch notes {#015}

- **Date**: 2026-05-06
- **Context**: Memory notes were plain markdown with no visual hierarchy. Section headers were hard to scan at a glance, especially in the site viewer and Obsidian.
- **Decision**: Use emojis in section headers of all Memory branch notes (e.g. `## 🔄 Recent Changes`, `## 🔗 See Also`). All agent contracts (AGENTS.md, CLAUDE.md, GEMINI.md, Codex) and `memory-writeback.mdc` now instruct this. No emojis in code, CLI output, or logs.
- **Status**: Active

## ✅ 016 - Decisions step in every memory-update template {#016}

- **Date**: 2026-05-06
- **Context**: The `/memory-update` command and all agent contracts only instructed agents to update branch notes. Architectural decisions were silently skipped, causing `decisions.md` to go stale.
- **Decision**: Every memory-update template and agent contract now has an explicit step: "If any architectural, design, or tooling decisions were made, add them to `decisions.md`."
- **Status**: Active

## 🔗 See Also

- [[architecture]] -- where these decisions are applied
- [[gotchas]] -- problems these decisions solve
