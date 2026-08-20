# Reference

Detailed guides for every feature. See the main [README](../README.md) for quick start and overview.

---

## Static site export

Build a polished standalone site from your knowledge vault -- no Obsidian required:

```bash
bedrock export-html       # generate
bedrock view              # generate and open in browser
bedrock view --serve      # generate and serve on http://127.0.0.1 (Ctrl-C to stop)
```

The generated site includes an overview page, branch tree navigation, note detail
view, evidence view, interactive graph view, and machine-readable `knowledge.json`
and `graph.json`. It writes to `Views/site/` by default, with legacy
`Outputs/site/` fallback for older projects. Opens via `file://` with no server needed;
use `--serve` (optionally with `--port`) when the browser restricts local files.

Memory/ notes are always primary. Evidence and generated view items are clearly marked
non-canonical.

## Lightweight sync output

`bedrock sync` keeps the active vault small. It refreshes:

- `Evidence/raw/git-recent.md` for a compact recent git snapshot
- `History/` for lightweight project chronology
- `Views/graph/knowledge-index.json` and `.md` for deterministic retrieval

It does **not** create per-sync capture YAML files by default.

## Progressive retrieval

The knowledge index (`Views/graph/knowledge-index.json` and `.md`) is regenerated
on every sync, with legacy `Outputs/` fallback for older projects. Agents can:

1. Load the index first (cheap, a few KB)
2. Identify relevant branches from the shortlist
3. Load only the full note content they actually need

Use `bedrock search <query>` for a quick shortlist query from the
command line or a hook.

## Clean web import

Import a web page as cleaned, non-canonical evidence:

```bash
bedrock clean-import https://docs.example.com/api-reference
# produces: bedrock/Evidence/imports/2025-01-15-api-reference.md
```

Strips navigation, ads, scripts, and boilerplate. Writes clean markdown with
YAML frontmatter marking it as non-canonical.

## Project history

`init` automatically backfills a lightweight legacy history layer when run on an existing repo.
You can also run it explicitly:

```bash
bedrock backfill-history
```

Creates `History/events.ndjson` (append-only event log), `History/history.md`
(human-readable summary), and `History/timeline/` (sparse milestone notes).

History records what happened over time -- releases, integrations, sync events.
It is not a git replacement. Current truth lives in `Memory/`, and current focus
lives in `Work/`.

## Keeping up to date

```bash
pip install -U project-bedrock
bedrock refresh-system
```

`refresh-system` updates all integration files -- Claude settings/commands/contract,
Cursor hooks/rules/commands, `AGENTS.md` header, Codex config -- and version markers.
It never touches `Memory/`, `Work/`, `Evidence/`, or any curated knowledge.

`bedrock doctor` warns when the project integration is behind the installed version.

### One-time fix for projects set up before 0.4.17

Versions before 0.4.17 wrote the setting-up machine's absolute repo path into
`.claude/settings.json`, `.cursor/hooks.json`, `.agent-project.yaml`, and
`bedrock/STATUS.md`, so every hook failed for everyone else who cloned the repo:

```
Error: Invalid value for '--project': Path '/home/someone/code/proj' does not exist.
```

0.4.17 generates hook commands with no path at all -- `bedrock sync` rather than
`bedrock sync --project <dir>` -- and the CLI walks up from wherever it was
invoked to find the project root. Nothing to hardcode, nothing to quote when the
path contains a space, and nothing that depends on the shell expanding a
variable (Windows hooks run under Git Bash or PowerShell, which disagree).

The repair ships via `refresh-system`, which normally runs from the
`SessionStart` hook -- the very hook that is broken. So run it by hand once per
repo, then commit:

```bash
bedrock refresh-system --project .
git commit -am "fix: portable bedrock integration files"
```

Project-added hooks, `permissions`, and `env` in `.claude/settings.json` are
preserved; only bedrock's own hook commands are rewritten.

### Layout versions

`bedrock/STATUS.md` records a `layout_version` -- an integer describing the
on-disk shape of the vault, separate from `framework_version`. Most releases
change no layout and leave it alone.

- **Your install is newer than the project:** `refresh-system` applies the
  pending migrations in order and records the new version. This happens
  automatically from the `SessionStart` hook.
- **Your install is older than the project:** both `sync` and `refresh-system`
  write nothing and tell you to upgrade. Without this, the older teammate would
  revert the layout on every session and the newer one would restore it,
  forever. The guard covers both because `SessionStart` runs them together as
  `bedrock sync && bedrock refresh-system` -- guarding only the second one
  would leave `sync` free to rewrite the vault first.

A blocked run still exits 0, because it happens in a session hook where a
non-zero exit would take the whole session down with it -- and where failing
`sync` would stop `refresh-system` from ever reporting why. `bedrock doctor`
reports which side of the gap you are on.

Migrations only ever move data; nothing is deleted, so
`refresh-system --dry-run` is safe to inspect first. A migration that fails
stops the chain and leaves the version unrecorded, so the next session retries
from the last good state -- the rest of the refresh still runs, and the failure
is reported rather than swallowed.

The guard only protects from 0.4.17 onward: an older install has no notion of
layout versions and will not honour it.

## Custom knowledge home

```bash
export AGENT_KNOWLEDGE_HOME=~/my-knowledge
bedrock init
```

## Troubleshooting

```bash
bedrock doctor          # validate setup and report health
bedrock doctor --json   # machine-readable health check
```

Common issues:
- `./bedrock` missing: run `bedrock init` (or `bedrock init --external` to keep knowledge outside the repo)
- Project still on external mode: run `bedrock migrate-to-local` to switch the vault into the repo
- Onboarding still pending: paste the init prompt into your agent
- Claude not picking up memory: check `.claude/settings.json` exists -- run `bedrock refresh-system`
- Cursor hooks not firing: check `.cursor/hooks.json` exists -- run `bedrock refresh-system`
- `Invalid value for '--project': Path ... does not exist` in a hook, or a path that stops at the first space: the repo was set up before 0.4.17, when hook commands still carried a path -- run `bedrock refresh-system --project .` once and commit the result (see "Keeping up to date")
- `bedrock view` opens nothing over plain SSH: the file lives on the remote host, so the message points at `bedrock view --serve` -- run that and forward the port. With a forwarded display (`ssh -X`) the browser opens as usual
- Stale index: run `bedrock sync`
- Large notes: run `bedrock compact`
- **Wrong binary**: another tool may install a Node.js `agent-knowledge` binary that shadows ours. Check with `which -a bedrock`. Fix: `export PATH="$(python3 -c 'import sysconfig; print(sysconfig.get_path("scripts"))'):$PATH"`

## Platform support

- **macOS** and **Linux** are fully supported.
- **Windows** is not currently supported (relies on `bash` and POSIX shell scripts).
- Python 3.9+ required.

## Migrating from agent-knowledge-cli

If you previously used the `agent-knowledge-cli` PyPI package, migration is three steps:

```bash
pip uninstall agent-knowledge-cli   # remove old package
pip install project-bedrock         # install new package
bedrock migrate-from-legacy         # update this project's hooks and rules
```

`migrate-from-legacy` runs `refresh-system` internally — it updates `.cursor/hooks.json`,
`settings.json`, rules, and command files so they call `bedrock` instead of `agent-knowledge`.

The `agent-knowledge` command still works as a deprecated alias. It will be removed
in a future release. Start using `bedrock` in scripts and habits now.

## Package naming

| What | Value |
|------|-------|
| PyPI package | `project-bedrock` |
| CLI command | `bedrock` (alias: `agent-knowledge`, deprecated) |
| Python import | `agent_knowledge` |

## Development

```bash
git clone <repo-url>
cd agent-knowledge
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest tests/ -q
```
