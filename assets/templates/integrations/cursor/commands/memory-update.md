Update the project cockpit.

Steps:
1. Run in terminal: `bedrock sync --project .`
2. Review what changed and what was learned
3. Update `./bedrock/Memory/` with stable, confirmed project knowledge -- put area-specific facts in that area's own doc (`Memory/<area>.md`), creating it if the area has none yet
4. Update `./bedrock/Work/NOW.md` if the current focus, next actions, or blockers changed
5. Update `./bedrock/Work/open-questions.md`, `./bedrock/Work/risks.md`, or `./bedrock/Work/backlog.md` if needed
6. Summarize what changed in Memory, what changed in Work, and what was intentionally skipped

Rules:
- Stable facts go into `Memory/`, in the doc for the area they belong to
- One doc per subsystem: `Memory/<area>.md` for the design, `Memory/decisions.md` for dated rationale, `Memory/PROJECT.md` for the cross-area overview only
- Current priorities and open loops go into `Work/`
- Generated site or graph output stays in `Views/`
- Do not dump raw session notes into the cockpit
