# Agent Knowledge

This project uses agent-knowledge for persistent project memory.
Read the root `AGENTS.md` for knowledge management instructions.
Check `./agent-knowledge/STATUS.md` for onboarding state.

If onboarding is pending, follow the instructions in the root AGENTS.md before other work.

## Session Start

Run at the beginning of each session:

```bash
agent-knowledge sync --project . && agent-knowledge refresh-system --project .
```

This syncs memory branches, rolls up sessions, refreshes git evidence, updates the knowledge index, and refreshes integration files.

## Memory Maintenance

After completing meaningful work in a session:

1. Write updated facts directly to `./agent-knowledge/Memory/<branch>.md`
   - Update the relevant branch note
   - Add a dated entry to the `Recent Changes` section
   - Update `./agent-knowledge/Memory/MEMORY.md` if branch summaries changed
2. Run `agent-knowledge sync --project .` to propagate changes

Write to memory when:
- An architectural decision was made
- A new command, module, or feature was completed
- A gotcha or constraint was discovered
- A pattern or convention was confirmed
- Test count or CI setup changed

## Periodic (every few sessions)

Run to keep integration files current with the installed framework:

```bash
agent-knowledge refresh-system --project .
```

Do NOT write to memory for:
- Read-only exploration with no conclusions
- Speculative or unconfirmed changes
- Session-specific context that won't matter next session

## Knowledge Structure

- `./agent-knowledge/Memory/` -- Canonical project knowledge (write here)
- `./agent-knowledge/Evidence/` -- Non-canonical: imports, extracts
- `./agent-knowledge/Outputs/` -- Generated views (never canonical)
- `./agent-knowledge/History/` -- Lightweight diary, events, releases
