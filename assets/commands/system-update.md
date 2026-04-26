# System Update

System Update refreshes the current project's agent-knowledge integration layer
to match the currently installed framework version.

It does not rebuild the ontology, re-import history, or modify curated project
knowledge. It only updates integration bridge files and metadata version markers.

## When to use

Use `/system-update` when:
- A new version of agent-knowledge has been installed (`pip install -U agent-knowledge-cli`)
- The doctor command reports that the project integration is stale
- Tool bridge files (Cursor hooks, CLAUDE.md, AGENTS.md header) may be outdated
- STATUS.md is missing `framework_version` (legacy project)
- You want to confirm the project is running the latest integration conventions

Do NOT use `/system-update` to:
- Rebuild the full ontology (use the `project-ontology-bootstrap` skill)
- Re-import project history (use `agent-knowledge import`)
- Rewrite Memory/ branches (use `memory-management` skill)

## What it updates

| Target | Action |
|--------|--------|
| `AGENTS.md` | Updates framework header; preserves project-specific `## TODO` section |
| `.cursor/hooks.json` | Replaces with current bundled template (with repo-path substitution) |
| `.cursor/rules/agent-knowledge.mdc` | Updates from current bundled template |
| `CLAUDE.md` | Updates if unchanged from template; warns if customized |
| `.codex/AGENTS.md` | Updates from current bundled template (if Codex detected) |
| `STATUS.md` | Adds/updates `framework_version` and `last_system_refresh` fields |
| `.agent-project.yaml` | Adds/updates `framework_version` field |

## What it never modifies

- `Memory/` — curated durable knowledge
- `Evidence/` — imported or extracted material
- `Outputs/` — generated views (except STATUS.md version fields)
- Any file not listed in the table above

## Behavior

1. Inspect current project integration state
2. Detect which tool integrations are installed (Cursor, Claude, Codex)
3. Compare each integration file with the currently bundled framework template
4. Update outdated files; skip up-to-date files; warn on customized files
5. Update STATUS.md `framework_version` and `last_system_refresh`
6. Report a clear summary: what was updated, what was skipped, any warnings

The command is idempotent. Running it when everything is current results in
all items reporting "up-to-date" and no files written.

## Expected CLI Entry Point

```bash
agent-knowledge refresh-system
agent-knowledge refresh-system --dry-run
agent-knowledge refresh-system --json
agent-knowledge refresh-system --project /path/to/repo
```

## After running

After a successful system update:
1. Check the summary for any warnings
2. If `CLAUDE.md` or `AGENTS.md` was flagged for manual review, inspect the diff
3. Re-run `agent-knowledge doctor` to confirm health
4. Commit the refreshed integration files with: `git add AGENTS.md .cursor/ && git commit -m "chore: refresh agent-knowledge integration"`
