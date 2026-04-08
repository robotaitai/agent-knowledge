# agents-rules

Framework repo for adaptive, file-based project knowledge.

The system is built around a strict split:

- `Memory/` is curated durable knowledge.
- `Evidence/` is imported or extracted material.
- `Outputs/` is generated orientation or helper material.
- `Outputs/` is never canonical truth by default.

## Architecture Overview

The v2 architecture has three layers:

1. Global framework repo
   This repo. It owns shared commands, rules, skills, templates, and scripts.
2. Dedicated project knowledge folder
   The real source of truth for a project's knowledge, typically under `~/agent-os/projects/<project-slug>/`.
3. Local project pointer
   Inside the app repo, `./agent-knowledge` is only a local pointer to that external folder.

All operational flows work through `./agent-knowledge` as the local handle.
The external folder remains the source of truth.

This repo does not:

- redesign the system into repo-local storage
- snapshot the knowledge vault back into the app repo
- treat generated outputs as durable memory automatically

## Quickstart

### After Cloning This Repo

```bash
./scripts/install-project-links.sh --help
./scripts/doctor.sh --help
./scripts/measure-token-savings.py --help
```

### Inside A Real Project Repo

```bash
/path/to/agents-rules/scripts/install-project-links.sh --slug my-project --repo .
/path/to/agents-rules/scripts/import-agent-history.sh .
/path/to/agents-rules/scripts/update-knowledge.sh .
/path/to/agents-rules/scripts/doctor.sh .
```

## Dedicated Folder And Local Pointer

Canonical layout:

```text
~/agent-os/projects/<project-slug>/      # real source of truth
/path/to/repo/agent-knowledge            # local pointer/symlink/junction
```

The local repo handle exists so agents, hooks, and humans can use stable in-repo paths like:

- `./agent-knowledge/INDEX.md`
- `./agent-knowledge/Memory/MEMORY.md`
- `./agent-knowledge/STATUS.md`

But the real content lives outside the repo.

## Knowledge Layout

```text
agent-knowledge/
  INDEX.md
  STATUS.md
  Memory/
    MEMORY.md
    decisions/
    tooling/
  Evidence/
    raw/
    imports/
      graphify/
    tooling/
  Sessions/
  Outputs/
    graphify/
    token-measurements/
  Dashboards/
  Templates/
  .obsidian/
```

Meaning:

- `Memory/`: curated durable notes with frontmatter and stable sections.
- `Evidence/raw/`: direct extracts from repo history, manifests, configs, workflows, and similar sources.
- `Evidence/imports/`: imported docs, traces, structural evidence, graph reports.
- `Sessions/`: temporary milestone-oriented session state.
- `Outputs/`: generated summaries, structural maps, token reports, and other orientation aids.
- `Dashboards/`: lightweight project rollups.
- `STATUS.md`: operational state for bootstrap, backfill, sync, compaction, validation, and doctor.

Confidence labels used in evidence and generated discovery notes:

- `EXTRACTED`: directly copied or listed from a source
- `INFERRED`: derived summary or architecture guess that still needs review
- `AMBIGUOUS`: incomplete, stale, or uncertain material such as sessions or traces

## Connect A Project

Connect a repo to its external knowledge folder:

```bash
scripts/install-project-links.sh --slug my-project --repo /path/to/repo
```

Optional flags:

- `--knowledge-home <dir>` changes the default external root. Default: `~/agent-os/projects`
- `--real-path <dir>` uses an explicit external folder
- `--install-hooks` installs a repo-local `.cursor/hooks.json`
- `--dry-run` previews changes

The install flow creates or verifies:

- the external knowledge folder
- the local `./agent-knowledge` pointer
- `.agent-project.yaml`
- `.agentknowledgeignore`
- `AGENTS.md`
- optional `.cursor/hooks.json`

## Bootstrap, Backfill, And Writeback

### Bootstrap

Bootstrap creates the adaptive knowledge tree and initial memory branches:

```bash
scripts/bootstrap-memory-tree.sh --project /path/to/repo
```

Bootstrap inspects repo structure, manifests, docs, configs, tests, and workflows to infer a profile such as:

- `web-app`
- `robotics`
- `ml-platform`
- `hybrid`

### Backfill

Backfill imports evidence without treating it as canonical memory:

```bash
scripts/import-agent-history.sh --project /path/to/repo
```

Backfill writes:

- repo extracts into `Evidence/raw/`
- docs, traces, structural notes, and graph imports into `Evidence/imports/`
- generated orientation notes into `Outputs/`

Curated promotion into `Memory/` still requires agent judgment.

### Ongoing Writeback

Ongoing project writeback happens through:

```bash
scripts/update-knowledge.sh --project /path/to/repo
```

It:

- inspects repo changes
- classifies affected memory branches
- appends recent change bullets where needed
- optionally records a decision note
- refreshes evidence imports
- updates `STATUS.md`

If no meaningful durable understanding changed, it should avoid unnecessary memory writes.

## Operational Flows

### Project Knowledge Sync

```bash
scripts/update-knowledge.sh --project /path/to/repo
```

Main reusable primitive for project-level sync. Suitable for manual use, hooks, and command docs.

### Global Tooling Sync

```bash
scripts/global-knowledge-sync.sh --project /path/to/repo
```

Scans safe allowlisted local tooling surfaces such as:

- `~/.claude/settings.json`
- `~/.claude/CLAUDE.md`
- `~/.claude/agents/**`
- `~/.codex/config.toml`

It writes:

- raw tooling evidence under `Evidence/tooling/`
- curated tooling notes under `Memory/tooling/`

It skips or redacts:

- secrets
- tokens
- auth/session material
- opaque caches

### Optional Graph / Structural Sync

```bash
scripts/graphify-sync.sh --project /path/to/repo
scripts/graphify-sync.sh --project /path/to/repo --dry-run
```

This flow is optional. It does not require `graphify` to be installed.

If graph-style artifacts are available, they are imported into:

- `Evidence/imports/graphify/`
- `Outputs/graphify/`

They stay evidence or outputs first. They are not promoted into `Memory/` automatically.

### Ship

```bash
scripts/ship.sh --project /path/to/repo
```

Ship runs:

- detected validations
- knowledge sync
- memory compaction
- git stage/commit/push
- optional PR creation

If the knowledge source of truth is external, ship reports that clearly instead of pretending those files were committed.

### Validation And Doctor

```bash
scripts/validate-knowledge.sh --project /path/to/repo
scripts/doctor.sh --project /path/to/repo
```

Use these when:

- setting up a project for the first time
- troubleshooting pointer issues
- checking frontmatter and required note sections
- verifying that commands, rules, and scripts point to real targets

## Token Savings Measurement

`scripts/measure-token-savings.py` supports two practical measurement modes.

### 1. Static Context Comparison

Compare a broad baseline context set against a memory-scoped set:

```bash
scripts/measure-token-savings.py compare \
  --project /path/to/repo \
  --baseline README.md docs src package.json \
  --optimized agent-knowledge/Memory/MEMORY.md agent-knowledge/Memory/architecture.md
```

Outputs:

- baseline token count
- optimized token count
- absolute savings
- percentage savings

Tokenizer behavior:

- `auto` prefers `tiktoken` `cl100k_base` if available
- otherwise it falls back to a `chars/4` estimate

This is a repo-controlled context estimate only. It does not claim to measure hidden provider-side token accounting.

### 2. Task-Run Logging Friendly Mode

Append file-based run entries for later comparison:

```bash
scripts/measure-token-savings.py log-run \
  --project /path/to/repo \
  --task fix-ci \
  --mode broad \
  --context README.md docs src

scripts/measure-token-savings.py log-run \
  --project /path/to/repo \
  --task fix-ci \
  --mode memory-scoped \
  --context agent-knowledge/Memory/MEMORY.md agent-knowledge/Memory/architecture.md
```

By default, entries go to:

```text
agent-knowledge/Outputs/token-measurements/task-run-log.jsonl
```

Optional summary:

```bash
scripts/measure-token-savings.py summarize-log --project /path/to/repo
```

## Dry-Run, Validation, And Safety

Write-oriented scripts support `--dry-run`:

- `scripts/install-project-links.sh`
- `scripts/bootstrap-memory-tree.sh`
- `scripts/import-agent-history.sh`
- `scripts/update-knowledge.sh`
- `scripts/global-knowledge-sync.sh`
- `scripts/graphify-sync.sh`
- `scripts/compact-memory.sh`
- `scripts/ship.sh`

Operational behavior:

- compare-before-replace writes
- idempotent reruns where practical
- lightweight cache signatures for evidence imports
- safe failure on broken pointer/setup state
- local handle must resolve to the external source-of-truth folder

## Hooks

Hook support is template-driven.

- template: `templates/hooks/hooks.json.template`
- repo-local install target: `.cursor/hooks.json`

Recommended hook pattern:

```json
{
  "hooks": [
    {
      "name": "project-knowledge-sync",
      "event": "post-write",
      "command": "/path/to/agents-rules/scripts/update-knowledge.sh --summary-file /path/to/repo/.cursor/knowledge-sync.last.json /path/to/repo"
    }
  ]
}
```

Keep hooks:

- lightweight
- reviewable
- easy to disable
- pointed at shared scripts instead of custom duplicated logic

## Example Flows

### 1. New Project Bootstrap

```bash
scripts/install-project-links.sh --slug my-project --repo /path/to/repo
scripts/bootstrap-memory-tree.sh --project /path/to/repo
```

### 2. Existing Project Onboarding

```bash
scripts/install-project-links.sh --slug my-project --repo /path/to/repo
scripts/import-agent-history.sh --project /path/to/repo
scripts/graphify-sync.sh --project /path/to/repo --dry-run
scripts/update-knowledge.sh --project /path/to/repo
```

### 3. Daily Usage

```bash
scripts/update-knowledge.sh --project /path/to/repo
scripts/ship.sh --project /path/to/repo
```

### 4. Global Tooling Sync

```bash
scripts/global-knowledge-sync.sh --project /path/to/repo
```

### 5. Troubleshooting

```bash
scripts/doctor.sh --project /path/to/repo
scripts/validate-knowledge.sh --project /path/to/repo
sed -n '1,200p' /path/to/repo/agent-knowledge/STATUS.md
```

## Obsidian Story

### Project-Level Vault

Open either:

- the real external folder, for example `~/agent-os/projects/my-project/`
- or the local repo pointer path, for example `/path/to/repo/agent-knowledge`

The project-level starter settings live under:

- `templates/project/agent-knowledge/.obsidian/`

### Portfolio / Umbrella Vault

Open the parent knowledge root itself, for example:

```text
~/agent-os/projects/
```

That gives one higher-level vault containing many project knowledge folders.

Use it for:

- portfolio dashboards
- recent decisions across projects
- projects needing doctor attention
- projects needing backfill or compaction

Lightweight portfolio templates live under:

- `templates/portfolio/INDEX.md`
- `templates/portfolio/Dashboards/INDEX.md`
- `templates/portfolio/.obsidian/`

This remains file-based and markdown-first. No database is added.

## Gitignore And Commit Guidance

Recommended noisy-path ignores for connected repos:

```gitignore
agent-knowledge/Evidence/
agent-knowledge/Sessions/
agent-knowledge/Outputs/
agent-knowledge/.obsidian/workspace*.json
agent-knowledge/.obsidian/cache/
```

Usually commit in the app repo:

- `.agent-project.yaml`
- `.agentknowledgeignore`
- `AGENTS.md`
- optional local pointer policy, if your team tracks the symlink/junction

Usually do not commit from the app repo:

- external knowledge vault contents
- generated evidence, sessions, and outputs
- machine-specific `.obsidian` workspace noise

## Example Snippets

### Example `.agent-project.yaml`

```yaml
project:
  name: accounter
  slug: accounter

knowledge:
  pointer_path: ./agent-knowledge
  real_path: /Users/taio/agent-os/projects/accounter
  memory_root: ./agent-knowledge/Memory/MEMORY.md
```

### Example Durable Memory Note

```markdown
---
note_type: durable-memory-branch
project: accounter
profile: web-app
area: architecture
status: active
last_updated: 2026-04-08
---

# Architecture

## Purpose

- Track the stable shape of the app and its major boundaries.

## Current State

- API server and frontend live in one workspace.

## Recent Changes

- 2026-04-08 - Synced after schema and workflow changes.

## Decisions

- Use dedicated decision notes for architecture shifts.

## Open Questions

- Which boundaries need tighter ownership notes?

## Subtopics

- [Stack](stack.md)
```

### Example Evidence Note

```markdown
---
note_type: structural-evidence
project: accounter
source: import-agent-history.sh
kind: structural-summary
confidence: EXTRACTED
generated_at: 2026-04-08T14:41:06Z
---

# Structural Evidence Summary

## Purpose

- Quick orientation note derived from direct repository scans.
```

### Example Token Measurement Report

```json
{
  "mode": "static-compare",
  "baseline": { "token_count": 12840 },
  "optimized": { "token_count": 2410 },
  "absolute_savings": 10430,
  "percentage_savings": 81.23
}
```

### Example `STATUS.md`

```markdown
- Last bootstrap: `2026-04-08T14:39:23Z`
- Last backfill/import: `2026-04-08T14:42:18Z`
- Last project sync: `2026-04-08T14:52:10Z`
- Last global sync: `2026-04-08T14:42:10Z`
- Last graph sync: `2026-04-08T14:41:07Z`
- Last validation: `2026-04-08T14:39:52Z` (`ok`)
```

## Templates And Commands

Templates:

- `templates/memory/`
- `templates/dashboards/`
- `templates/project/`
- `templates/portfolio/`

Command docs mirror the operational scripts:

- `commands/knowledge-sync.md`
- `commands/global-knowledge-sync.md`
- `commands/graphify-sync.md`
- `commands/ship.md`
- `commands/doctor.md`

## OS Caveats

- macOS may normalize `/tmp` into `/private/tmp`; scripts account for that when resolving the external folder.
- Windows-style environments may require Developer Mode or elevated permissions for symlinks. A junction may be needed when symlink creation is blocked.

## Philosophy

The system stays:

- file-based
- explicit about evidence vs memory vs outputs
- compatible with Obsidian
- operationally scriptable
- lightweight enough to review by hand
