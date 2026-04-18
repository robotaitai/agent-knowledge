# agent-knowledge

Persistent, file-based project memory for AI coding agents.

One command gives any project a knowledge vault that agents read on startup,
maintain during work, and carry across sessions -- no database, no server,
just markdown files and a CLI.

Works with **Claude Code**, **Cursor**, and **Codex** out of the box.

## Install

```bash
pip install agent-knowledge-cli
```

PyPI package name: `agent-knowledge-cli`. CLI command and all docs: `agent-knowledge`.

## Quick Start

```bash
cd your-project
agent-knowledge init
```

That's it. Open the project in Claude Code or Cursor and the agent has
persistent memory automatically -- no manual prompting, no config, no setup.

`init` does everything in one shot:
- creates an external knowledge vault at `~/agent-os/projects/<slug>/`
- symlinks `./agent-knowledge` into the repo as the local handle
- installs project-local integration for both Claude Code and Cursor
- detects Codex and installs its bridge files if present
- bootstraps the memory tree and marks onboarding as `pending`
- imports repo history into `Evidence/` and backfills lightweight history from git

## How It Works

Knowledge lives **outside** the repo at `~/agent-os/projects/<slug>/` so it persists
across branches, tools, and clones. The symlink `./agent-knowledge` gives every tool
a stable local handle.

### Knowledge layers

| Folder | Role | Canonical? |
|--------|------|-----------|
| `Memory/` | Curated, durable facts -- source of truth | Yes |
| `History/` | What happened over time -- lightweight diary | Yes (diary) |
| `Evidence/` | Imported/extracted material, event stream | No |
| `Outputs/` | Generated views, indexes, HTML export | No |
| `Sessions/` | Ephemeral session state, prune aggressively | No |

Evidence is never auto-promoted into Memory. Outputs are never treated as truth.
Only agents and humans deliberately write to Memory or History.

## Project-local integration

The project carries everything it needs. Both Claude Code and Cursor get full
integration installed automatically -- hooks, runtime contracts, and slash commands.
No global config required.

## Obsidian-ready

The knowledge vault at `~/agent-os/projects/<slug>/` is a valid Obsidian vault.
Open it directly for backlinks, graph view, and note navigation.

![Obsidian graph view of a project knowledge vault](docs/obsidian-graph.png)

For a spatial canvas of the knowledge graph:

```bash
agent-knowledge export-canvas
# produces: agent-knowledge/Outputs/knowledge-export.canvas
```

The vault is designed to work well in Obsidian -- good markdown, YAML frontmatter,
branch-note convention, internal links. But everything works without it too.

### What gets installed

**Claude Code** (`.claude/`):

| File | Purpose |
|------|---------|
| `settings.json` | Lifecycle hooks: sync on SessionStart, Stop, PreCompact |
| `CLAUDE.md` | Runtime contract: knowledge layers, session protocol, onboarding |
| `commands/memory-update.md` | `/memory-update` slash command |
| `commands/system-update.md` | `/system-update` slash command |

**Cursor** (`.cursor/`):

| File | Purpose |
|------|---------|
| `rules/agent-knowledge.mdc` | Always-on rule: loads memory context on every session |
| `hooks.json` | Lifecycle hooks: sync on start, update on write, sync on stop/compact |
| `commands/memory-update.md` | `/memory-update` slash command |
| `commands/system-update.md` | `/system-update` slash command |

**Codex** (`.codex/`) -- installed when detected:

| File | Purpose |
|------|---------|
| `AGENTS.md` | Agent contract with knowledge layer instructions |

### Session lifecycle

Hooks fire automatically -- the agent syncs memory at the start of every session    
and captures state at the end, with no manual intervention:

| Event | Claude Code | Cursor | What runs |
|-------|-------------|--------|-----------|
| Session start | SessionStart | session-start | `agent-knowledge sync` |
| File saved | -- | post-write | `agent-knowledge update` |
| Task complete | Stop | stop | `agent-knowledge sync` |
| Context compaction | PreCompact | preCompact | `agent-knowledge sync` |

The runtime contract ensures the agent reads `STATUS.md` and `Memory/MEMORY.md`
at the start of every session, with no manual prompting required.

### Slash commands

Inside any Claude Code or Cursor session:

- `/memory-update` -- sync, review session work, write stable facts to `Memory/`, summarize
- `/system-update` -- refresh integration files to the latest framework version

These are project-local and work automatically because `init` installed them.

### Integration health

```bash
agent-knowledge doctor
```

Reports whether all integration files (settings, hooks, rules, commands) are
installed and current for both Claude Code and Cursor. If anything is stale or
missing, `doctor` tells you exactly what to run.

## Commands

| Command | What it does |
|---------|-------------|
| `init` | Set up a project -- one command, no arguments needed |
| `sync` | Full sync: memory, history, git evidence, index |
| `doctor` | Validate setup, integration health, version staleness |
| `ship` | Validate + sync + commit + push |
| `search <query>` | Search the knowledge index (Memory-first) |
| `export-html` | Build a polished static site from the vault |
| `view` | Build site and open in browser |
| `clean-import <url>` | Import a URL as cleaned, non-canonical evidence |
| `refresh-system` | Refresh all integration files to the current framework version |
| `backfill-history` | Rebuild lightweight project history from git |
| `compact` | Prune stale captures and old session state |

All write commands support `--dry-run` and `--json`. Run `agent-knowledge --help` for the full list.



## Static site export

Build a polished standalone site from your knowledge vault -- no Obsidian required:

```bash
agent-knowledge export-html       # generate
agent-knowledge view              # generate and open in browser
```

The generated site includes an overview page, branch tree navigation, note detail
view, evidence view, interactive graph view, and machine-readable `knowledge.json`
and `graph.json`. Opens via `file://` with no server needed.

Memory/ notes are always primary. Evidence and Outputs items are clearly marked
non-canonical.

## Automatic capture

Every sync and update event is automatically recorded in `Evidence/captures/`
as a small structured YAML file. This gives a lightweight history of what
changed and when -- without a database or background service.

Captures are evidence, not memory. They accumulate quietly and can be pruned
with `agent-knowledge compact`.

## Progressive retrieval

The knowledge index (`Outputs/knowledge-index.json` and `.md`) is regenerated
on every sync. Agents can:

1. Load the index first (cheap, a few KB)
2. Identify relevant branches from the shortlist
3. Load only the full note content they actually need

Use `agent-knowledge search <query>` for a quick shortlist query from the
command line or a hook.

## Clean web import

Import a web page as cleaned, non-canonical evidence:

```bash
agent-knowledge clean-import https://docs.example.com/api-reference
# produces: agent-knowledge/Evidence/imports/2025-01-15-api-reference.md
```

Strips navigation, ads, scripts, and boilerplate. Writes clean markdown with
YAML frontmatter marking it as non-canonical.

## Project history

`init` automatically backfills a lightweight history layer when run on an existing repo.
You can also run it explicitly:

```bash
agent-knowledge backfill-history
```

Creates `History/events.ndjson` (append-only event log), `History/history.md`
(human-readable summary), and `History/timeline/` (sparse milestone notes).

History records what happened over time -- releases, integrations, sync events.
It is not a git replacement. Current truth lives in `Memory/`.

## Keeping up to date

```bash
pip install -U agent-knowledge-cli
agent-knowledge refresh-system
```

`refresh-system` updates all integration files -- Claude settings/commands/contract,
Cursor hooks/rules/commands, `AGENTS.md` header, Codex config -- and version markers.
It never touches `Memory/`, `Evidence/`, `Sessions/`, or any curated knowledge.

`doctor` warns when the project integration is behind the installed version.

## Custom knowledge home

```bash
export AGENT_KNOWLEDGE_HOME=~/my-knowledge
agent-knowledge init
```

## Troubleshooting

```bash
agent-knowledge doctor          # validate setup and report health
agent-knowledge doctor --json   # machine-readable health check
```

Common issues:
- `./agent-knowledge` missing: run `agent-knowledge init`
- Onboarding still pending: paste the init prompt into your agent
- Claude not picking up memory: check `.claude/settings.json` exists -- run `agent-knowledge refresh-system`
- Cursor hooks not firing: check `.cursor/hooks.json` exists -- run `agent-knowledge refresh-system`
- Stale index: run `agent-knowledge sync`
- Large notes: run `agent-knowledge compact`
- **Wrong binary**: another tool may install a Node.js `agent-knowledge` that shadows ours. Check with `which -a agent-knowledge`. Fix: `export PATH="$(python3 -c 'import sysconfig; print(sysconfig.get_path("scripts"))'):$PATH"`

## Platform support

- **macOS** and **Linux** are fully supported.
- **Windows** is not currently supported (relies on `bash` and POSIX shell scripts).
- Python 3.9+ required.

## Package naming

| What | Value |
|------|-------|
| PyPI package | `agent-knowledge-cli` |
| CLI command | `agent-knowledge` |
| Python import | `agent_knowledge` |

## Development

```bash
git clone <repo-url>
cd agent-knowledge
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest tests/ -q
```
