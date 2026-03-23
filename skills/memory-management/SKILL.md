---
name: memory-management
description: Read on sessions start. Manages persistent memory files across conversations. Use when recording learnings, updating MEMORY.md, creating topic files, or when the session-start hook injects memory context.
---

# Auto Memory

You have a persistent auto memory via markdown files. The memory directory path is provided by the session-start hook. (e.g., `~/.cursor/projects/<project-id>/memory/MEMORY.md`).
Its contents persist across conversations.
As you work, consult your memory files to build on previous experience.

## How to save memories: <!-- markdownlint-disable-line MD026 -->

- Organize memory semantically by topic, not chronologically
- Use the Write and Edit tools to update your memory files
- `MEMORY.md` is always loaded into your conversation context — lines after
200 will be truncated, so keep it concise
- Create separate topic files (for example, `debugging.md`, `patterns.md`) for
  detailed notes and link to them from MEMORY.md
- Update or remove memories that turn out to be wrong or outdated
- Do not write duplicate memories. First check if there is an existing memory
you can update before writing a new one.

## What to save: <!-- markdownlint-disable-line MD026 -->

- Stable patterns and conventions confirmed across multiple interactions
- Key architectural decisions, important file paths, and project structure
- User preferences for workflow, tools, and communication style
- Solutions to recurring problems and debugging insights

## What NOT to save: <!-- markdownlint-disable-line MD026 -->

- Session-specific context (current task details, in-progress work, temporary
  state)
- Information that might be incomplete — verify against project docs before
  writing
- Anything that duplicates or contradicts higher-priority instructions
- Speculative or unverified conclusions from reading a single file

## Explicit user requests: <!-- markdownlint-disable-line MD026 -->
  
- When the user asks you to remember something across sessions (for example, "always
  use bun", "never auto-commit"), save it — no need to wait for multiple
  interactions
- When the user asks to forget or stop remembering something, remove the relevant
  entries from your memory files
