---
area: packaging
updated: 2026-04-08
---

# Packaging

## Purpose
Python packaging strategy for making agent-knowledge pip-installable.

## Current State

- Build backend: `hatchling` via `pyproject.toml`.
- Layout: `src-layout` at `src/agent_knowledge/`.
- Entry point: `agent-knowledge = agent_knowledge.cli:main` in `[project.scripts]`.
- Runtime dependency: `click>=8.0`. Optional: `tiktoken` (for token measurement), `pytest>=7.0` + `build` (dev).
- All non-Python assets consolidated under a single top-level `assets/` directory (scripts, templates, rules, rules-global, commands, skills, skills-cursor, claude). Bundled into `agent_knowledge/assets/` via `[tool.hatch.build.targets.wheel.force-include]`.
- sdist includes `src/`, `assets/`, `tests/`, and metadata files via `[tool.hatch.build.targets.sdist.include]`.
- Version: `0.0.1` (tagged `v0.0.1`).

## Recent Changes

- 2026-04-08: Initial packaging created. Chose hatchling over setuptools for simpler asset bundling with force-include.
- 2026-04-08: Consolidated all asset directories (scripts, templates, rules, etc.) from repo root into single `assets/` directory.
- 2026-04-08: Updated `force-include` paths from e.g. `"scripts"` to `"assets/scripts"`.
- 2026-04-08: Version set to `0.0.1` (initially was `0.1.0`, corrected per user request).

## Decisions

- Chose `hatchling` over `setuptools` because `force-include` cleanly maps repo-root asset directories into the package without MANIFEST.in complexity.
- Chose `src-layout` to avoid import confusion between repo root and installed package.
- Did not use `importlib.resources` -- scripts derive their own paths from SCRIPT_DIR, so a simple `Path(__file__)` approach in `runtime/paths.py` is sufficient.

## Gotchas

- macOS system Python refuses `pip install` with "externally managed" error. Use brew python + `--user --break-system-packages`, or a venv.
- pip may silently skip extracting certain file types (e.g. `.mdc`) from wheels during editable installs. Workaround: inline critical content in Python code rather than depending on template files.
- Editable installs (`pip install -e .`) reflect Python source changes live, but changes to `assets/` require a rebuild (`python -m build`).
- Venv can get corrupted if multiple Python versions coexist in `.venv/lib/`. Fix: `rm -rf .venv` and recreate with an explicit python version.
- Old system pip (e.g. 21.2.4) doesn't support PEP 660 editable installs with `pyproject.toml`. Need pip >= 21.3.

## Open Questions

- None currently.
