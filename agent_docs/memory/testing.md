---
area: testing
updated: 2026-04-13
---

# Testing

## Purpose
Test strategy for packaging validation and CLI correctness.

## Current State

- Framework: `pytest` (dev dependency).
- **162 tests** across 2 files: `tests/test_packaging.py` and `tests/test_cli.py`.
- CI: GitHub Actions (`.github/workflows/ci.yml`) -- ubuntu-latest + macos-latest, Python 3.10/3.12/3.13.
  - `test` job: runs `pytest` with editable install.
  - `build` job: builds wheel, installs from wheel, runs CLI smoke tests (`--help`, `--version`, subcommand `--help`).

### test_packaging.py
- Verifies package is importable and `__version__` exists.
- Verifies `get_assets_dir()` resolves without error.
- Checks all bundled scripts, common lib, templates, rules, and commands exist at expected paths under assets.
- Verifies `get_script()` returns valid paths and raises `FileNotFoundError` for missing scripts.
- Verifies `capture`, `index`, and `viewer` modules are importable.
- Verifies `Evidence/captures/README.md` template is bundled.

### test_cli.py
- Top-level `--help` and `--version`.
- Parametrized `--help` for all 21 subcommands (including `search`, `index`, `export-html`, `view`, `clean-import`, `export-canvas`, `refresh-system`, `backfill-history`).
- `init --help` contains `--slug`.
- `init --dry-run` exits 0 and does not create files.
- `doctor --json` output is valid JSON with `"script": "doctor"`.
- Smoke test: `init` in tmp repo -> verifies symlink and `.agent-project.yaml` created -> `doctor --json` returns clean result.
- `measure-tokens` with no args shows help text.
- All sync tests: copies memory branches, extracts git log, stamps STATUS.md, JSON output.
- Capture: sync creates `.yaml` in `Evidence/captures/`, not in `Memory/`, idempotent within same minute, dry-run safe.
- Index: sync creates `Outputs/knowledge-index.json` and `.md`, Memory notes marked canonical, Evidence/Outputs non-canonical.
- Search: returns results, prefers Memory/ over other folders.
- Export-HTML: creates standalone HTML with badges and non-canonical warnings, idempotent, dry-run safe.
- Hooks: `.cursor/hooks.json` uses CLI commands (not raw script paths), has required fields.
- Package naming: `pyproject.toml` name is `agent-knowledge-cli`, scripts entry is `agent-knowledge`.
- Skills: all 12 expected skill files exist, have frontmatter, and `SKILLS.md` index is present.
- `obsidian-compatible-writing` skill is marked optional.
- `clean-import`: imports HTML file, strips nav, does not write to Memory/, dry-run safe, JSON output.
- `export-canvas`: creates valid Canvas JSON in Outputs/, dry-run safe, includes Memory/ nodes, not in Memory/.
- Core CLI flow: `init -> sync -> doctor` still works; new commands do not create non-markdown files in Memory/.
- `refresh-system`: runs without error, produces clean JSON, dry-run safe, idempotent, never touches Memory/, updates STATUS.md/project-yaml version fields, bundled `system-update.md` exists and is discoverable.
- `export-html` graph: `graph.json` created, project node present, canonical distinction enforced, edges reference valid nodes, graph tab in HTML, GRAPH_DATA embedded and parseable, dry-run safe, JSON mode includes graph counts.

### Running tests
- All tests run via the installed package (`python -m agent_knowledge` or editable install).
- `BIN = [sys.executable, "-m", "agent_knowledge"]` ensures tests use the current Python interpreter.
- Helper `_init_repo(tmp_path)` creates a git-initialized temp directory for test isolation.

## Recent Changes

- 2026-04-08: Initial test suite created (27 tests).
- 2026-04-08: Added 11 new tests for zero-arg init, integrations, onboarding (total: 38).
- 2026-04-08: Added GitHub Actions CI workflow.
- 2026-04-10: Added 31 new tests for capture, index, search, export-html, hooks, naming (total: 69).
- 2026-04-10: Added 22 new tests for skills, clean-import, export-canvas, core CLI stability (total: 91).
- 2026-04-10: Added 6 new tests for site generator (export-html), replaced old viewer tests (total: 97).
- 2026-04-10: Added 11 new tests for refresh-system command (total: 108).
- 2026-04-10: Added 10 new tests for graph view in site export (total: 118).
- 2026-04-11: Added 9 new tests for backfill-history / history layer, +1 for new subcommand help (total: 128).
- 2026-04-12: Added 15 new cursor-integration tests (commands install, hook events, check_cursor_integration, rule content) + 2 packaging tests (total: 145).
- 2026-04-13: Added 17 new Claude integration tests (settings.json, commands, check_claude_integration, health checks) (total: 162).

## Open Questions

- None currently.
