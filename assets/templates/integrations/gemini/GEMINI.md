# bedrock

This project uses **bedrock** as a small project cockpit for AI-agent work.
All project context lives in `./bedrock/`.

## On session start

1. Read `./bedrock/STATUS.md`
2. If `onboarding: pending` — read `AGENTS.md` and follow First-Time Onboarding
3. If `onboarding: complete` — read `./bedrock/Memory/PROJECT.md`
4. Read `./bedrock/Work/NOW.md`
5. Load only the relevant Memory branches for the current task

## Project cockpit

- `Memory/` = what the project knows
- `Work/` = what matters now
- `Views/` = generated human inspection views

Legacy folders such as `History/`, `Evidence/`, `Outputs/`, or `Sessions/`
may still exist for compatibility.

## After meaningful work

1. Update stable project knowledge in `./bedrock/Memory/`
2. Update current priorities and open loops in `./bedrock/Work/`
3. Run `bedrock sync --project .`

## How Memory is split

Memory is organized per area, one doc per subsystem:

- `Memory/<area>.md` = everything durable about that area (navigation, perception, auth, billing, ...). If work touches an area with no doc yet, create it.
- `Memory/decisions.md` = dated rationale for choices, not the design itself
- `Memory/PROJECT.md` = cross-area overview only; it links to the area docs

Name areas after the project's own functional layers, not its hardware or file
layout, so cross-cutting subsystems get a home instead of being scattered.
