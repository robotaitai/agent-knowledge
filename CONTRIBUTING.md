# Contributing to Project Bedrock

Thanks for wanting to contribute.

Project Bedrock is a team-lead layer for AI agents. Its job is to make AI-assisted development more continuous, understandable, and reviewable.

The core idea is simple:

> Every session should leave the project smarter.

That means contributions should not only add code. They should also improve the project’s memory, architecture, documentation, tests, and handoff quality.

---

## What Project Bedrock is

Project Bedrock gives a repo structured project memory for humans and AI agents.

It helps agents and developers keep track of:

- architecture
- decisions
- conventions
- history
- evidence
- generated outputs
- session handoffs

It integrates with tools like Claude Code, Cursor, and Codex, but the core remains simple:

- markdown files
- git-friendly structure
- a Python CLI
- project-local runtime contracts
- no required database
- no required server
- no hosted backend

---

## Contribution principles

Please keep these principles in mind.

### 1. Preserve the trust model

Project Bedrock separates project knowledge by purpose.

| Layer | Role | Canonical? |
|---|---|---|
| `Memory/` | Stable project truth, decisions, architecture, conventions | Yes |
| `Memory/Team/` | Normalized team consensus reached through managed dialogue | Yes |
| `Memory/Members/<id>/` | A single member's own perspective (person or agent) | No — perspective, not consensus |
| `History/` | What happened over time | Yes, as a diary |
| `Evidence/` | Raw or imported supporting material | No |
| `Outputs/` | Generated views, indexes, HTML, graphs | No |
| `Sessions/` | Temporary working state | No |

Do not treat imported evidence or generated outputs as truth. A member's
perspective in `Members/` is not team truth until it graduates into `Team/`.

Only deliberately curated knowledge belongs in `Memory/`.

### 2. Keep hooks thin

Hooks should trigger behavior, not contain the whole system.

Good hooks:

- detect project context
- call the installed CLI
- no-op when nothing changed
- preserve state before compaction
- trigger lightweight sync/update behavior

Bad hooks:

- rebuild the whole ontology every time
- re-import all history repeatedly
- rewrite large parts of memory for small edits
- contain lots of duplicated logic

The CLI/runtime should stay the engine.

### 3. Keep the project-local contract primary

Project Bedrock should work from the project itself.

Prefer project-local files such as:

- `.claude/`
- `.cursor/`
- `.codex/`
- `AGENTS.md`
- project metadata
- local `agent-knowledge/` or future `bedrock/` knowledge folder

Avoid designs that depend only on global home-directory configuration.

Global setup may help, but the project should carry its own contract.

### 4. Avoid hardcoded project ontologies

Do not force every repo into the same structure.

A robotics repo may organize memory around:

- perception
- navigation
- localization
- safety

A SaaS repo may organize memory around:

- frontend
- backend
- auth
- billing
- data

The ontology should be inferred from the real project, not forced from a generic template.

### 5. Make AI work cumulative

A good contribution should help answer at least one of these questions:

- What changed?
- Why did it change?
- Where should the next agent start?
- What decision was made?
- What is stable truth vs temporary evidence?
- What should a new contributor know before touching this area?

---

## Ways to contribute

Good contribution areas include:

- CLI improvements
- Cursor / Claude / Codex integration
- hook lifecycle improvements
- memory update pipeline
- history and evidence handling
- HTML / graph / canvas exports
- documentation and examples
- tests and smoke tests
- onboarding UX
- packaging and release workflow
- better project diagnostics via `doctor`
- migration and compatibility tooling

Small, focused PRs are preferred.
