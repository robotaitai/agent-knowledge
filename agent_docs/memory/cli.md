---
area: cli
updated: 2026-04-08
---

# CLI

## Purpose
Design and implementation of the `agent-knowledge` command-line interface.

## Current State

- Framework: `click` with a `@click.group()` top-level and 13 subcommands.
- Subcommands: init, setup, bootstrap, import, update, doctor, validate, ship, global-sync, graphify-sync, compact, measure-tokens.
- Pattern: thin Python wrappers that parse CLI args, then delegate to bundled shell scripts via `run_bash_script()` / `run_python_script()` from `runtime/shell.py`.
- `setup` is pure Python (replaced root `install.sh`): symlinks global Cursor rules/skills and runs Claude config install.
- Common flags: `--dry-run`, `--json`, `--force` propagated via `_add_common_flags()`.
- `--summary-file` on `update` command (hidden) supports hook integration.
- `measure-tokens` uses `context_settings={"allow_interspersed_args": False}` so `--help` and subcommand args pass through to the delegated `measure-token-savings.py` script instead of being consumed by click.

### init command (zero-arg)
- `--slug` defaults to sanitized repo directory name (`_sanitize_slug` helper).
- `--repo` defaults to `.` (cwd).
- `--knowledge-home` defaults from `AGENT_KNOWLEDGE_HOME` env var or `~/agent-os/projects`.
- Auto-detects Cursor/Claude/Codex integrations and installs bridge files (via `runtime/integrations.py`).
- `--no-integrations` flag to skip auto-detection.
- Prints a cyan-bordered "flashy" prompt after setup suggesting the user's next step:
  `Read AGENTS.md and ./agent-knowledge/STATUS.md, then onboard this project.`
- Uses `click.secho` with `fg="cyan"` and `bold=True` for styled output.

## Recent Changes

- 2026-04-08: Created CLI with 11 subcommands.
- 2026-04-08: Added `setup` command (pure Python, replaced root `install.sh`).
- 2026-04-08: Made `init` zero-arg with slug inference and auto-detection.
- 2026-04-08: Added multi-tool integration detection/install to `init`.
- 2026-04-08: Added cyan-bordered prompt output after `init`.
- 2026-04-08: Fixed `measure-tokens --help` passthrough with `allow_interspersed_args=False`.

## Decisions

- Scripts are invoked via subprocess, not reimplemented in Python. **Why:** The scripts are complex, battle-tested, and self-contained. Rewriting would introduce bugs for no gain. **How to apply:** Only rewrite a script if it fundamentally can't work from the installed package.
- `measure-tokens` passes all args unprocessed to the underlying Python script. **Why:** The script has its own argparse subcommands (compare, log-run, summarize-log) with their own `--help`.
- `setup` was implemented in pure Python (not a shell wrapper). **Why:** The old `install.sh` was just symlinking and calling another script; Python handles this cleanly and avoids shipping a root-level script.
- `init` defaults were chosen to eliminate friction: the normal path is just `agent-knowledge init` with no flags.

## Open Questions

- None currently.
