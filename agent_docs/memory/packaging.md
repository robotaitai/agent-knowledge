---
note_type: durable-branch
area: packaging
updated: 2026-04-13
tags:
  - agent-knowledge
  - memory
  - packaging
---

# Packaging

Python [[stack|packaging]] strategy for making agent-knowledge pip-installable.

## Build System

- Backend: **hatchling** via `pyproject.toml`
- Layout: src-layout at `src/agent_knowledge/`
- Entry point: `agent-knowledge = agent_knowledge.cli:main`

## Asset Bundling

All non-Python assets consolidated under `assets/` at repo root. Bundled into wheel via `[tool.hatch.build.targets.wheel.force-include]`:
- `assets/scripts` -> `agent_knowledge/assets/scripts`
- `assets/templates` -> `agent_knowledge/assets/templates`
- `assets/rules` -> `agent_knowledge/assets/rules`
- (and rules-global, commands, skills, skills-cursor, claude)

See [[architecture#Path Resolution]] for how the code finds these at runtime.

## Version

Current: **0.2.5**. PyPI package name: `agent-knowledge-cli`. See [[deployments]].

Install: `pip install agent-knowledge-cli`. Command: `agent-knowledge`.

PyPI credentials stored in `~/.pypirc` (mode 600). Upload: `python -m twine upload dist/agent_knowledge_cli-<ver>*`.

**Gotcha**: editable install (`pip install -e .`) copies assets into `.venv/site-packages/` at install time. Script edits under `assets/scripts/` require re-running `pip install -e .` to propagate to the venv copy. See [[gotchas]].

## Dependencies

See [[stack#Dependencies]] for the full list.

## See Also

- [[stack]] -- runtimes and frameworks
- [[architecture]] -- package layout
- [[gotchas]] -- pip installation pitfalls
- [[decisions#001|Decision: hatchling over setuptools]]
