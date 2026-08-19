---
note_type: durable-branch
area: gotchas
updated: 2026-08-20
tags:
  - agent-knowledge
  - memory
  - gotchas
update_when: >
  A new non-obvious bug is hit and fixed; a workaround is discovered for a
  platform or environment issue; an existing gotcha is resolved and no longer
  applies.
---

# ⚠️ Gotchas

Known pitfalls, traps, and non-obvious behaviors.

## 🐚 Shell Scripts

- `set -euo pipefail` + trailing `[ "$DRY_RUN" -eq 1 ] && log ...` causes exit 1 when test is false. Use `if/then` instead. See [[conventions]].
- `ship.sh` uses `python -m pytest -q` not bare `pytest` -- bare `pytest` fails outside venvs. See [[testing]].
- `kc_normalize_relative_path` returns via a caller-named variable (`kc_normalize_relative_path out "$path"`), NOT stdout. Never call it with `$(...)` -- the stdout form was removed because command-substitution forks made init 16s (agent-knowledge-3x7). `KC_IGNORE_PATTERNS` entries are pre-normalized at load time.
- `import-agent-history.sh` `list_top_level_dirs` dies silently (grep -Ev matches nothing → pipefail → set -e) on repos where every top-level dir is filtered, and `init` swallows the failure. Open: agent-knowledge-10p.
- `kc_yaml_leaf_value` strips a trailing `\r`, so CRLF checkouts (Git for Windows autocrlf) parse clean frontmatter values. Fixed 2026-08-20 (agent-knowledge-2fy).

## 🐍 Python / pip

- macOS system Python refuses `pip install` ("externally managed"). Use brew python + `--user --break-system-packages`, or a venv. See [[stack]].
- Old system pip (e.g. 21.2.4) doesn't support PEP 660 editable installs with `pyproject.toml`. Need pip >= 21.3.
- Venv can get corrupted if multiple Python versions coexist in `.venv/lib/`. Fix: `rm -rf .venv` and recreate with explicit version.

## 📦 [[packaging|Packaging]]

- [[architecture|hatchling]] editable installs copy `src/` files to `site-packages`. Changes to `assets/` require rebuild to take effect in the wheel. Source Python files update live.
- pip may silently skip extracting `.mdc` files from wheels. Workaround: [[integrations|inline critical content in Python code]]. See [[decisions#006]].

## 🔄 Sync

- `stamp_status` regex must use `[ \t]*` not `\s*` to avoid eating newlines across YAML frontmatter fields. Fixed in `runtime/sync.py`.

## 🐍 Python Version Compatibility

- **f-string backslash (Python < 3.12)**: `re.sub(r'...', '', val)` cannot be called directly inside an f-string `{}` on Python 3.10/3.11 — raises `SyntaxError: f-string expression part cannot include a backslash`. Extract the call to a local variable first. Fixed in `runtime/site.py` (2026-04-28). Python 3.12+ relaxed this restriction.

## 🪟 Windows Encoding

- **cp1255 / system locale crash**: On Windows with a non-UTF-8 system locale (e.g. Hebrew cp1255), Python uses the locale encoding for `read_text()` / `write_text()` by default. Every file I/O call across `cli.py`, `sync.py`, `index.py`, `capture.py`, `history.py`, `integrations.py`, `refresh.py`, `absorb.py` now explicitly passes `encoding="utf-8"`. Fixed in v0.4.4.

## 🌐 Site / JS

- **Wikilink stem regex** (`findNoteBySlug` in `site.py` HTML template): inside a Python raw string, `\\.md` outputs `\\.md` to JS which matches a literal backslash, not a dot. Correct Python raw string: `\.md` → JS sees `\.md` = literal dot. Fixed in v0.4.3.

## 🚀 CI / PyPI

- **Trusted publishing broken**: PyPI trusted publisher config does not match the workflow. Publishing is done manually via twine. To fix: remove the trusted publisher on PyPI and re-add it without an environment field. See [[packaging#PyPI Publish]].

## 🍎 Rosetta / Apple Silicon

- An x86_64 Python (this repo's `.venv` is one) runs under Rosetta 2 on Apple Silicon, and its children get the x86_64 slice of universal binaries -- bash and everything it forks run translated at ~7x cost (measured: same script 14.1s translated vs 1.9s native). `run_bash_script` in `runtime/shell.py` escapes via `arch -arm64` when `sysctl.proc_translated` is 1. pytest itself still runs translated; rebuilding `.venv` with an arm64 python would speed the suite ~7x.

## 🕓 Recent Changes

- 2026-04-28: Documented f-string backslash `SyntaxError` on Python < 3.12; fixed in `runtime/site.py`.
- 2026-05-05: Documented Windows cp1255 encoding crash; fixed in v0.4.4. Documented JS wikilink regex bug; fixed in v0.4.3. Documented PyPI trusted publishing breakage.
- 2026-08-20: Fixed CRLF leak in `kc_yaml_leaf_value` (agent-knowledge-2fy) and the 16s init (agent-knowledge-3x7: fork-per-call in the path filter + Rosetta-translated bash children). Documented the Rosetta section and the `list_top_level_dirs` silent-death pitfall (agent-knowledge-10p).

## 🔗 See Also

- [[conventions]] -- rules designed to avoid these
- [[testing]] -- tests that catch regressions
- [[decisions|Decisions]] -- why certain workarounds exist
