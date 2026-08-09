# bedrock

This project uses **bedrock** as a small project cockpit for AI-agent work.
All project context lives in `./bedrock/`.

## Project cockpit

- `Memory/` = what the project knows
- `Work/` = what matters now
- `Views/` = generated human inspection views

Legacy folders such as `History/`, `Evidence/`, `Outputs/`, or `Sessions/`
may still exist for compatibility. They are not the main user-facing model.

## On session start

If `./bedrock/` does not exist but `./agent-knowledge/` does, this project needs migration:

```bash
bedrock migrate-vault && bedrock refresh-system
```

Otherwise:

1. Read `./bedrock/STATUS.md`
2. If `onboarding: pending` -- read `AGENTS.md` and perform First-Time Onboarding
3. If `onboarding: complete` -- read `./bedrock/Memory/PROJECT.md`
4. Read `./bedrock/Work/NOW.md`
5. Load only the relevant Memory branches for the task

## After meaningful work

- Update stable project knowledge in `./bedrock/Memory/`
- Update current priorities and open loops in `./bedrock/Work/`
- Run `/memory-update`

## How Memory is split

Memory is organized per area, one doc per subsystem:

- `Memory/<area>.md` -- everything durable about that area (navigation, perception, auth, billing, ...). If work touches an area with no doc yet, create it.
- `Memory/decisions.md` -- dated rationale for choices, not the design itself
- `Memory/PROJECT.md` -- cross-area overview only; it links to the area docs

Name areas after the project's own functional layers, not its hardware or file
layout, so cross-cutting subsystems get a home instead of being scattered.

## Periodic

- Run `/system-update` every few sessions to refresh integration files

## When the context window is getting long

- Run `/compact-context`

## Generated site

`bedrock view` builds a styled HTML site from the vault with emoji icons, TOC, Mermaid diagram rendering, and wikilink navigation. These are HTML-only features — plain-text rules (no emojis in code/responses) do not apply to the generated site.
