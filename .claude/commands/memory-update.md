Perform a project memory update.

Steps:
1. Run in terminal: `agent-knowledge sync --project .`
2. Review this session's work and identify what stable project knowledge changed
3. For each changed area, update the relevant `./agent-knowledge/Memory/<branch>.md`:
   - Edit the Current State section with confirmed facts
   - Add a dated entry to Recent Changes: `YYYY-MM-DD -- what changed`
4. If branch summaries changed, update `./agent-knowledge/Memory/MEMORY.md`
5. Summarize: what branches were updated, what was skipped, and why

Write to Memory only for stable, confirmed facts. Skip speculative or session-only context.
Evidence and captures go to `Evidence/`, not `Memory/`.
