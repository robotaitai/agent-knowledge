---
note_type: durable-branch
area: conventions
updated: 2026-05-06
tags:
  - agent-knowledge
  - memory
  - conventions
update_when: >
  A new coding pattern or naming rule is established and agreed on; an existing
  convention is changed intentionally; a new Memory note type is introduced.
---

# 📐 Conventions

Coding patterns, naming, and design rules.

## 🏷️ Naming

- [[cli|CLI]] command names use **hyphens**: `bedrock graphify-sync`
- Python package uses **underscores**: `agent_knowledge`
- User-facing messages reference CLI commands, never script paths

## 🧩 Code Patterns

- Shell scripts stay in `assets/scripts/`, invoked via `runtime/shell.py`
- Templates use `<placeholder>` syntax for substitution
- No emojis in code, logs, or CLI output

## 📝 Memory Notes

- Require YAML frontmatter: `note_type`, `area`/`project`, `updated`, `tags`
- `durable-branch` notes must include an `update_when` field in frontmatter: a plain-English description of the conditions that should trigger an update to that note. This tells agents when to revisit without requiring them to understand the whole codebase.
- `doctor` automatically detects potentially stale notes by comparing the note's `updated` date against `git log` on the source paths registered for that area in `refresh._NOTE_AREA_PATHS`. When adding a new durable-branch area, add a corresponding entry there.
- Use wiki-links (`[[note-name]]`) for Obsidian graph connectivity — they become edges in the graph view
- Use emojis in section headers for scannability (e.g. `## 🔄 Recent Changes`, `## 🔗 See Also`)
- [[MEMORY|Evidence and Outputs]] are never treated as curated truth

## 🐚 Shell Scripts

- Always `set -euo pipefail`
- Avoid `[ test ] && cmd` -- use `if/then` (see [[gotchas]])
- Find assets via `SCRIPT_DIR`, never hardcode paths

## 🕓 Recent Changes

- 2026-04-28: Added `update_when` convention for all `durable-branch` notes; `doctor` uses it to detect stale notes.
- 2026-04-28: Documented that each area in `refresh._NOTE_AREA_PATHS` must have a matching durable-branch entry.
- 2026-05-06: Emoji convention added — use emojis in Memory note section headers for scannability. No emojis in code, logs, or CLI output.

## 🔗 See Also

- [[architecture]] -- how patterns are applied
- [[gotchas]] -- things that break these conventions
- [[cli]] -- CLI naming examples
