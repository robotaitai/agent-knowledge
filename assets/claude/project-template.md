# Project: <Name>

<!-- Drop this file at the project root as CLAUDE.md -->
<!-- It is read automatically by Claude Code at the start of every session -->
<!-- Global rules in ~/.claude/CLAUDE.md are also loaded — no need to repeat them here -->

## Stack

- <language/runtime>
- <framework>
- <database>
- <key libraries>

## Key Directories

- `src/` — <description>
- `tests/` — <description>

## Conventions

- <naming conventions>
- <patterns to follow>
- <patterns to avoid>

## What NOT to do

- Do not install <X> — we use <Y> instead
- Do not restructure <X> without asking
- Do not commit secrets — use .env.template as reference

## When unsure

- Search the codebase first. Reuse existing patterns.
- Ask before creating new packages or major abstractions.
- Read docs in `docs/` or `agent-knowledge/` before implementing.

## Shared Memory

Persistent project memory lives in `bedrock/Memory/`, organized one doc per area:

- `bedrock/Memory/<area>.md` — everything durable about that subsystem (navigation, perception, auth, billing, ...). If work touches an area with no doc yet, create it.
- `bedrock/Memory/decisions.md` — dated rationale for choices, not the design itself
- `bedrock/Memory/PROJECT.md` — cross-area overview only; it links to the area docs

Read the areas relevant to the task at the start of each session, and write back
after meaningful changes.

- If `bedrock/Memory/PROJECT.md` is missing: run `bedrock bootstrap --project .`
- After any architectural decision: use the `decision-recording` skill
- After any meaningful state change: follow the `memory-writeback` rule
- To backfill from git/docs history: run `bedrock import --project .`
