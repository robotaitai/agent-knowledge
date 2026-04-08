---
area: testing
updated: 2026-04-08
---

# Testing

## Purpose
Test strategy for packaging validation and CLI correctness.

## Current State

- Framework: `pytest` (dev dependency).
- 38 tests across 2 files: `tests/test_packaging.py` and `tests/test_cli.py`.
- CI: GitHub Actions (`.github/workflows/ci.yml`) -- ubuntu-latest + macos-latest, Python 3.10/3.12/3.13.
  - `test` job: runs `pytest` with editable install.
  - `build` job: builds wheel, installs from wheel, runs CLI smoke tests (`--help`, `--version`, subcommand `--help`).

### test_packaging.py
- Verifies package is importable and `__version__` exists.
- Verifies `get_assets_dir()` resolves without error.
- Checks all bundled scripts, common lib, templates, rules, and commands exist at expected paths under assets.
- Verifies `get_script()` returns valid paths and raises `FileNotFoundError` for missing scripts.

### test_cli.py
- Top-level `--help` and `--version` (asserts `0.0.1`).
- Parametrized `--help` for all 13 subcommands (including `setup`).
- `init --help` contains `--slug`.
- `init --dry-run` exits 0 and does not create files.
- `doctor --json` output is valid JSON with `"script": "doctor"`.
- Smoke test: `init` in tmp repo -> verifies symlink and `.agent-project.yaml` created -> `doctor --json` returns clean result.
- `measure-tokens` with no args shows help text.
- `test_init_infers_slug_from_dirname`: verifies slug derived from directory name.
- `test_init_zero_arg_from_cwd`: verifies `init` works with no explicit args.
- `test_init_installs_cursor_hooks`: verifies `.cursor/hooks.json` created.
- `test_init_installs_claude_bridge_when_detected`: verifies `CLAUDE.md` created when `.claude/` exists.
- `test_init_installs_codex_bridge_when_detected`: verifies `.codex/AGENTS.md` created when `.codex/` exists.
- `test_init_multi_tool_detection`: verifies all three tools detected simultaneously.
- `test_init_idempotent`: verifies re-running `init` is safe.
- `test_init_sets_onboarding_pending`: verifies `onboarding: pending` in STATUS.md after init.
- `test_agents_md_has_onboarding_instructions`: verifies AGENTS.md contains onboarding content.
- `test_doctor_json_includes_integrations`: verifies `doctor --json` reports integrations and onboarding state.

### Running tests
- All tests run via the installed package (`python -m agent_knowledge` or editable install).
- `BIN = [sys.executable, "-m", "agent_knowledge"]` ensures tests use the current Python interpreter.
- Helper `_init_repo(tmp_path)` creates a git-initialized temp directory for test isolation.

## Recent Changes

- 2026-04-08: Initial test suite created (27 tests).
- 2026-04-08: Added 11 new tests for zero-arg init, integrations, onboarding (total: 38).
- 2026-04-08: Added GitHub Actions CI workflow.

## Open Questions

- None currently.
