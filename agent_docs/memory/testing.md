---
note_type: durable-branch
area: testing
updated: 2026-05-06
tags:
  - agent-knowledge
  - testing
update_when: >
  New test functions are added or removed; the CI matrix changes (Python versions
  or OS targets); a new command is parametrized into the help-smoke tests.
  Run `grep -c "def test_" tests/test_cli.py tests/test_packaging.py` for the
  live count.
---

# 🧪 Testing

## 🎯 Purpose

Test strategy for packaging validation and CLI correctness.

## 📊 Current State

- Framework: `pytest` (dev dependency).
- **151 tests** across 2 files: `tests/test_packaging.py` (23) and `tests/test_cli.py` (~128).
- CI: GitHub Actions (`.github/workflows/ci.yml`) -- ubuntu-latest + macos-latest, Python 3.9/3.12/3.13.
  - `test` job: runs `pytest` with editable install.
  - `build` job: builds wheel, installs from wheel, runs CLI smoke tests (`--help`, `--version`, subcommand `--help`).

### 📦 test_packaging.py

- Verifies package is importable and `__version__` exists.
- Verifies `get_assets_dir()` resolves without error.
- Checks all bundled scripts, common lib, templates, rules, and commands exist at expected paths under assets.
- Verifies `get_script()` returns valid paths and raises `FileNotFoundError` for missing scripts.
- Verifies `capture`, `index`, and `viewer` modules are importable.
- Verifies `Evidence/captures/README.md` template is bundled.

### 🛠️ test_cli.py

- Top-level `--help` and `--version`.
- Parametrized `--help` for all 23 subcommands (including `absorb`, `migrate-to-local`, `search`, `index`, `export-html`, `view`, `clean-import`, `export-canvas`, `refresh-system`, `backfill-history`).
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
- Package naming: `pyproject.toml` name is `project-bedrock`, scripts entry is `agent-knowledge`.
- Skills: all expected skill files exist, have frontmatter, and `SKILLS.md` index is present.
- `clean-import`: imports HTML file, strips nav, does not write to Memory/, dry-run safe, JSON output.
- `export-canvas`: creates valid Canvas JSON in Outputs/, dry-run safe, includes Memory/ nodes, not in Memory/.
- Core CLI flow: `init -> sync -> doctor` still works; new commands do not create non-markdown files in Memory/.
- `refresh-system`: runs without error, produces clean JSON, dry-run safe, idempotent, never touches Memory/, updates STATUS.md/project-yaml version fields, bundled `system-update.md` exists and is discoverable.
- `export-html` graph: `graph.json` created, project node present, canonical distinction enforced, edges reference valid nodes, graph tab in HTML, GRAPH_DATA embedded and parseable, dry-run safe, JSON mode includes graph counts.
- **Claude integration**: `init` installs Claude settings, hooks, commands, and CLAUDE.md; refresh-system updates Claude config; doctor reports Claude health; smoke test `init -> doctor` with Claude.
- **absorb**: help, dry-run no mutation, imports docs and docs/ dir, metadata header present, ADRs parsed into decisions.md, idempotent, manifest created and not in Memory/, JSON mode, exits nonzero without vault, skips vault files itself.

### ▶️ Running tests

- All tests run via the installed package (`python -m agent_knowledge` or editable install).
- `BIN = [sys.executable, "-m", "agent_knowledge"]` ensures tests use the current Python interpreter.
- Helper `_init_repo(tmp_path)` creates a git-initialized temp directory for test isolation.

## 🕓 Recent Changes

- 2026-04-08: Initial test suite created (27 tests).
- 2026-04-08: Added 11 new tests for zero-arg init, integrations, onboarding (total: 38).
- 2026-04-08: Added GitHub Actions CI workflow.
- 2026-04-10: Added 31 new tests for capture, index, search, export-html, hooks, naming (total: 69).
- 2026-04-10: Added 22 new tests for skills, clean-import, export-canvas, core CLI stability (total: 91).
- 2026-04-10: Added 6 new tests for site generator (export-html), replaced old viewer tests (total: 97).
- 2026-04-10: Added 11 new tests for refresh-system command (total: 108).
- 2026-04-10: Added 10 new tests for graph view in site export (total: 118).
- 2026-04-11: Added 9 new tests for backfill-history / history layer, +1 for new subcommand help (total: 128).
- 2026-04-23: Added Claude integration tests (total: ~143).
- 2026-04-28: Added absorb tests (total: 153).
- 2026-04-30: Fixed all CI failures from v0.4.0 rename: updated ~80 path refs (`agent-knowledge` → `bedrock`), `is_symlink()` → `is_dir()` for local mode, content string checks, STATUS.md timestamp regex. CI now green (151 passing).
- 2026-05-06: Fixed `test_bundled_captures_readme_exists` — template path updated from `project/agent-knowledge/` to `project/bedrock/` (v0.4.10).

## ❓ Open Questions

- None currently.
