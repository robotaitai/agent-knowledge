# /absorb

Absorb existing project knowledge artifacts into the vault.

## Steps

1. Run in terminal: `agent-knowledge absorb --project .`
2. Read `./agent-knowledge/Outputs/absorb-manifest.md` to see what was imported
3. For each imported file in `Evidence/imports/`, extract stable facts:
   - If it contains architecture decisions → update `Memory/decisions/decisions.md`
   - If it describes a system component → update or create the relevant `Memory/<branch>.md`
   - If it contains changelog/history → verify `History/events.ndjson` was updated
4. Update `Memory/MEMORY.md` if new branches were created
5. Run `/memory-update` to sync and summarize changes

## Notes

- Imported files land in `Evidence/imports/` as non-canonical evidence
- `absorb` never writes directly to `Memory/` — that is the agent's job
- Re-running `absorb` is safe (idempotent); already-imported files are skipped
- Use `--no-decisions` to skip ADR parsing
- Use `--dry-run` to preview what would be imported
