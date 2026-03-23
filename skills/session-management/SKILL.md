---
name: session-management
description: Read on session start. Tracks work progress in session files during conversations. Use when recording milestones, decisions, blockers, or when the session-start hook creates a session file.
---

# Session Management

Session files preserve high-signal context through long sessions and compaction, then help new sessions resume quickly from prior work. The session file path is provided by the session-start hook (e.g., `~/.cursor/projects/<project-id>/sessions/`).

## Session File

- Filename format: `YYYY-MM-DD-<title-slug>-<UUID>.tmp`
- Default slug is `session` until renamed by session-manager at session end
- Keep sections concise: Current State, Completed, In Progress, Blockers, Notes for Next Session, Context to Load, Session Log
- Update `Last Updated` on each write
- Update or remove session entries when they become inaccurate, outdated, or superseded.
- Hook reminders/compact notifications are prompts to evaluate progress, not mandatory writes.
- Use the Write and Edit tools to update session files.

```markdown
## Current State
[One-line current focus]

### Completed
- [Milestone outcomes only]
```

## How to Update

1. Read the current session file first.
2. Compare current state with the latest session-log entry.
3. If no meaningful change happened, skip writing.
4. If meaningful change happened, write one concise checkpoint update:
   - refresh Current State
   - update Completed/In Progress/Blockers as needed
   - add one timestamped Session Log line
5. Set session title once the task is clear.
6. Keep updates natural and milestone-oriented (not every small step).

## Log Entry Template

```markdown
**HH:MM** - [Milestone outcome in one line]
```
