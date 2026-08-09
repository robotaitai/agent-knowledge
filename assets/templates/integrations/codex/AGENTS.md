# Agent Knowledge: <project-name>

This project uses **Project Bedrock** as a small project cockpit for AI-agent work.
All project context lives in `./bedrock/`.

## Session Start

1. Read `./bedrock/STATUS.md`
2. If `onboarding: pending` — follow **First-Time Onboarding** below
3. If `onboarding: complete` — read `./bedrock/Memory/PROJECT.md`
4. Read `./bedrock/Work/NOW.md`
5. Load only the relevant Memory branches for the current task

Run at session start if shell is available:

```bash
bedrock sync --project .
```

---

## First-Time Onboarding

Only run this if `STATUS.md` shows `onboarding: pending`. Do NOT redo it if already complete.

1. Inspect project structure: manifests, package files, CI/CD config, docs
2. Review recent git history (last ~50 commits)
3. Infer functional domains from the repo using the project's own terminology
4. Create Memory branches only where the repo actually needs them
5. Update `./bedrock/Memory/PROJECT.md` with durable project context
6. Update `./bedrock/Work/NOW.md` with the current focus and next recommended actions
7. Set `onboarding: complete` in `./bedrock/STATUS.md`

Rules:
- Memory must be project-shaped
- Only confirmed facts go into `Memory/`
- Raw material stays in `Evidence/`
- Generated views stay in `Views/`
- Do not read the whole vault unless necessary

---

## Project Cockpit

| Folder | Purpose | Canonical? |
|--------|---------|:----------:|
| `Memory/` | Stable project knowledge | Yes |
| `Work/` | Current priorities and open loops | Yes |
| `Views/` | Generated site and graph views | No |
| `History/` | Legacy diary layer | Yes |
| `Evidence/` | Raw imports and extracts | No |
| `Outputs/` | Legacy generated artifacts | No |

---

## Memory Update

After meaningful work:

1. Update the affected `./bedrock/Memory/<area>.md` docs with stable project knowledge
2. Update `./bedrock/Work/NOW.md` if priorities or next actions changed
3. Update `./bedrock/Work/open-questions.md`, `./bedrock/Work/risks.md`, or `./bedrock/Work/backlog.md` if needed
4. Run `bedrock sync --project .`

Do not dump raw session notes into the cockpit.

---

## How Memory Is Split

Memory is organized per area, one doc per subsystem:

| File | Holds |
|------|-------|
| `Memory/<area>.md` | Everything durable about that area (navigation, perception, auth, billing, ...) |
| `Memory/decisions.md` | Dated rationale for choices, not the design itself |
| `Memory/PROJECT.md` | Cross-area overview only; links to the area docs |

If work touches an area with no doc yet, create `Memory/<area>.md`. Name areas
after the project's own functional layers, not its hardware or file layout, so
cross-cutting subsystems get a home instead of being scattered.
