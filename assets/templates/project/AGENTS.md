# Agent Knowledge: <project-name>

This project uses **agent-knowledge** for persistent project memory.
All knowledge is accessed through `./agent-knowledge/` (symlink to external vault).

## First-Time Onboarding

Check `./agent-knowledge/STATUS.md`. If `onboarding: pending`:

1. Inspect project structure: manifests, package files, CI/CD config, docs
2. Inspect project-local tool config: `.cursor/`, `.claude/`, `.codex/` if present
3. Review recent git history (last ~50 commits, key branches)
4. Import findings into `Evidence/raw/` using `agent-knowledge import`
5. Infer the project ontology from the actual repo -- use the project's own
   functional domains as branch names (e.g., perception, navigation, localization),
   not generic categories (e.g., architecture, conventions)
6. Create one branch note per functional domain. Each note should be focused
   and under ~150 lines. Do NOT put the whole system description in one file.
7. Link related notes to each other with relative markdown links
8. Update `Memory/MEMORY.md` with links to all new branches
9. Update `./agent-knowledge/STATUS.md`: set `onboarding: complete`

## Branch Convention

Use the same-name branch-note pattern:

```
Memory/
  MEMORY.md                    # root -- always read first
  stack.md                     # flat note when no subtopics needed
  perception/
    perception.md              # entry note = same name as folder
    fusion.md                  # subtopic note
    lane-detection.md
  navigation/
    navigation.md
    path-following.md
  localization/
    localization.md
  decisions/
    decisions.md               # decision log
    2025-01-15-use-raw-sql.md  # individual decision
```

Rules:
- Each branch = one focused functional domain from the project
- Use the project's own terminology, not generic templates
- Each note stays under ~150 lines. If a topic is too big, split it.
- Link between related notes with relative markdown links (e.g.,
  `See [perception](perception/perception.md) for sensor details`)
- Small topic with no subtopics: one flat note (`stack.md`)
- Bigger topic: folder + same-name entry note (`perception/perception.md`)
- Do not create deep trees automatically -- grow only when justified
- Do NOT lump unrelated subsystems into a single "architecture" note.
  Split by functional domain instead.

## Onboarding Rules

- Only write confirmed facts to `Memory/` -- never speculate
- Keep raw/extracted material in `Evidence/`, not `Memory/`
- Keep generated views in `Outputs/` -- never treat as canonical truth
- Do NOT redo onboarding if STATUS.md already shows `onboarding: complete`

## Session Start

If you support shell commands, run at session start:

```bash
agent-knowledge sync --project .
```

## Memory Maintenance

After meaningful work, update `./agent-knowledge/Memory/` directly:

1. Edit the relevant branch note (`Memory/cli.md`, `Memory/architecture.md`, etc.)
   - Update `Current State` with confirmed facts (replace stale entries, no duplicates)
   - Add a `YYYY-MM-DD -- what changed` line to `Recent Changes`
2. Update `Memory/MEMORY.md` if branch one-line summaries changed
3. Run `agent-knowledge sync --project .` to propagate and refresh indexes

Write to memory when:
- A new feature, command, or module was completed
- An architectural decision was made or changed
- A gotcha, constraint, or pattern was confirmed
- Test coverage or CI configuration changed

Skip writeback for read-only sessions, speculative changes, or session-specific context.

## Ongoing Maintenance

After onboarding is complete, during normal work:
- Keep `Evidence/` and `Outputs/` separate from `Memory/` (never promote)
- Do NOT rebuild the knowledge tree every session
- Record architectural decisions in `Memory/decisions/`

## Knowledge Structure

- `Memory/` -- Curated, durable project knowledge (source of truth)
- `Evidence/` -- Imported/extracted material (not curated truth)
- `Outputs/` -- Generated helper views (never canonical)
- `STATUS.md` -- Onboarding and maintenance state
- `.agent-project.yaml` -- Project configuration

## Reading Order

1. `Memory/MEMORY.md` -- always read first
2. Relevant branch entry notes (e.g., `perception/perception.md`)
3. Leaf notes only if the specific detail is needed
4. Keep context lean -- do not read branches unrelated to the current task
