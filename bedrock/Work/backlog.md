---
project: agent-knowledge
updated: 2026-08-20
---

# Backlog

Use this for useful future work. Keep it short and reviewable.

## Open

- [ ] Retire the legacy `agent-knowledge/` vault once all durable context is confirmed present in `bedrock/`.
- [ ] Audit remaining user-facing docs for stale references to `Outputs/knowledge-index.*` and sync capture files.
- [ ] agent-knowledge-10p: `import-agent-history.sh` dies silently when no top-level dir survives the grep filter, and `init` hides the nonzero exit (found 2026-08-20 while fixing 3x7).

## Later

- [ ] Revisit whether `History/` should stay as a top-level compatibility layer or eventually be folded into the public cockpit story more explicitly.
