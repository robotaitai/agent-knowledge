# Agent Knowledge: <project-name>

This project uses **Project Bedrock** as a small project cockpit for AI-agent work.
All project context lives under `./bedrock/`.

## Project Cockpit

- `Memory/` = what the project knows
- `Work/` = what matters now
- `Views/` = generated human inspection views

Legacy folders such as `History/`, `Evidence/`, `Outputs/`, or `Sessions/`
may still exist for compatibility. They are not the main user-facing model.

## First-Time Onboarding

Check `./bedrock/STATUS.md`. If `onboarding: pending`:

1. Inspect project structure: manifests, package files, CI/CD config, docs
2. Inspect project-local tool config: `.cursor/`, `.claude/`, `.codex/` if present
3. Review recent git history (last ~50 commits, key branches)
4. Infer the project shape from the actual repo
5. Create Memory branches using the repo's real domains, not generic templates
6. Update `Memory/PROJECT.md` with durable project context
7. Update `Work/NOW.md` with the current focus and next recommended actions
8. Update `./bedrock/STATUS.md`: set `onboarding: complete`

## Memory Rules

- Memory must be project-shaped
- Do NOT force generic folders like `engineering/`, `testing/`, `release/`, or `setup/` unless the repo actually needs them
- Use the project's own terminology for Memory branches
- Only write confirmed, stable facts into `Memory/`
- Do not read the whole vault unless necessary

### One doc per area

Memory is organized per area, one doc per subsystem:

| File | Holds |
|------|-------|
| `Memory/<area>.md` | Everything durable about that area (navigation, perception, auth, billing, ...) |
| `Memory/decisions.md` | Dated rationale for choices, not the design itself |
| `Memory/PROJECT.md` | Cross-area overview only; links to the area docs |

If work touches an area with no doc yet, create `Memory/<area>.md`. Name areas
after the project's own functional layers, not its hardware or file layout, so
cross-cutting subsystems (navigation, control, auth) get a home instead of being
split between the project overview and the decisions log.

## Session Start

If you support shell commands, run at session start:

```bash
bedrock sync --project .
```

Then read:

1. `Memory/PROJECT.md`
2. `Work/NOW.md`
3. Only the relevant Memory branches for the current task

Do not treat generated Views as canonical truth.

## Updating The Cockpit

After meaningful work:

1. Update the affected `Memory/<area>.md` docs with stable project knowledge, creating any area doc that does not exist yet
2. Update `Work/NOW.md` if focus, next actions, or blockers changed
3. Update `Work/open-questions.md`, `Work/risks.md`, or `Work/backlog.md` if needed
4. Run `bedrock sync --project .`

Write to Memory when:
- A new feature, command, or module was completed
- An architectural decision was made or changed
- A gotcha, constraint, or pattern was confirmed
- Test coverage or CI configuration changed

Skip writeback for read-only sessions, speculative changes, or session-specific context.

## Knowledge Structure

- `Memory/` -- Curated, durable project knowledge
- `Work/` -- Current priorities and open loops
- `Views/` -- Generated site and graph views
- `History/` -- Legacy diary layer, still supported
- `Evidence/` -- Imported/extracted material, not curated truth
- `Outputs/` -- Legacy generated artifacts, still supported
- `STATUS.md` -- Onboarding and maintenance state
- `.agent-project.yaml` -- Project configuration
