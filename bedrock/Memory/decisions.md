---
note_type: decisions-index
updated: 2026-05-17
tags:
  - agent-knowledge
  - memory
  - decision
---

# Decisions

Use this file for important project decisions.

## Decision format

### YYYY-MM-DD, Decision title

**Decision:** What was decided.

**Why:** Why this decision was made.

**Impact:** What this changes.

**Related files:** Links to relevant Memory or Work items.

## Current decisions

### 2026-05-17, Clean the active Bedrock vault around Memory / Work / Views

**Decision:** Treat `bedrock/` as the active vault, preserve older history and imported evidence by copying the missing durable material from the legacy `agent-knowledge/` tree, stop creating per-sync capture YAML files, and write the compact retrieval index under `Views/graph/` instead of legacy `Outputs/`.

**Why:** The active vault had accumulated generated noise and duplicated history across two trees. The cleanup keeps older context available while making the working cockpit smaller and easier for agents to load.

**Impact:** `bedrock sync` no longer recreates `Evidence/captures/`; `Views/graph/knowledge-index.*` becomes the default deterministic retrieval index; `History/` and `Evidence/imports/` carry the older preserved context inside the active vault.

**Related files:** [PROJECT](PROJECT.md), [architecture](architecture.md), [cli](cli.md), [history-layer](history-layer.md), [Now](../Work/NOW.md)

### 2026-08-10, Generated hooks carry no project path

**Decision:** Hook commands written into `.claude/settings.json` and `.cursor/hooks.json` pass no `--project` argument at all -- `bedrock sync`, not `bedrock sync --project <dir>`. `_resolve_project()` walks up from the invocation directory to the nearest `.agent-project.yaml`. A relative `--summary-file` resolves against that root rather than the cwd.

**Why:** A path in a tracked, generated hook has to be right on every teammate's machine (GH #15, #17), survive spaces (GH #9), and expand in whichever shell the agent picked. The tempting fix -- quoting `"${CLAUDE_PROJECT_DIR:-.}"` -- fails the third test: Claude Code falls back to PowerShell on Windows when Git Bash is absent, where that expands to an empty string. Hooks also run in whatever cwd the agent was in, so a bare `.` is wrong too. Removing the argument satisfies all three at once.

**Impact:** `_GENERATED_HOOK_COMMANDS` in `runtime/refresh.py` must list every historical command shape so existing checkouts self-heal on the next session; a command a project *extended* is left alone. Never reintroduce a path into a hook template.

**Related files:** [cli](cli.md), [integrations](integrations.md), [gotchas](gotchas.md)

### 2026-08-10, Browser launches go through one display-guarded, non-blocking opener

**Decision:** All browser launches route through `runtime/shell.py: open_in_browser()`. It returns False when there is no display (SSH, or Linux without `DISPLAY`/`WAYLAND_DISPLAY`) so the caller prints the path instead, honors `$BROWSER`, spawns via `Popen` without waiting, and discards the launcher's output.

**Why:** Three separate failure modes, one seam. A failed launcher's stderr arrives after the shell prompt has returned and corrupts the next prompt (GH #18). Waiting on the launcher stalls callers that still have work to do -- `bedrock view --serve` had a port left to bind, and on a GUI-less macOS box `open` blocks long enough to break it. Ignoring `$BROWSER` makes tests launch real browsers.

**Impact:** No module may call `webbrowser.open` or shell out to `open`/`xdg-open` directly. `bedrock view` gained `--no-open` and `--serve`.

**Related files:** [cli](cli.md), [gotchas](gotchas.md)

## Legacy detailed log

Older numbered decisions remain in [decisions/decisions.md](decisions/decisions.md) for compatibility and historical reference.
