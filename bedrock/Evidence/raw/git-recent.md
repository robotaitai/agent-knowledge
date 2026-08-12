---
note_type: evidence
source: git-log
extracted: 2026-08-11T00:37:46Z
commits: 30
---

# Recent Git History

Last 30 commits as of 2026-08-11.

```
7fa6b7a chore: sync vault
c98c3f4 chore: export beads issues
f2bfa9d fix: guard sync against a newer project layout
e34521c fix: Path.write_text(newline=) requires Python 3.10, project supports 3.9
2afd94f chore: sync vault after the 0.4.17 work
0db67ad docs: document team-portable hooks and layout versions in the README
36ae351 fix: preserve STATUS.md keys on CRLF files and pin LF on write
a40e7b2 docs: explain layout versions and the no-downgrade rule
18692a9 fix: preserve unknown STATUS.md frontmatter keys when rewriting
dc0c0f0 feat: report blocked and degraded refreshes without failing the session
f0f854d fix: prove the blocked refresh writes nothing and report the on-disk layout
2190270 feat: run layout migrations from refresh-system and refuse to downgrade
39b94f3 revert: real_path healing is an invariant, not a layout migration
ff677ea refactor: move real_path localization into layout migration 1
0393be7 fix: stamp independently of pending work and report stamp failures
0f726c3 feat: add an ordered idempotent migration runner
e674e0e fix: scope layout version reads to frontmatter and report stamp failures
8f885bd feat: record an on-disk layout version separate from the package version
076a0c7 docs: record the no-path-in-hooks and single-browser-opener decisions
2540c99 test: make the --serve check proxy-independent and report the server's output
643d302 fix: spawn the browser launcher instead of waiting on it; honor $BROWSER
8c79a9c fix: drop the project path from generated hooks; repair update for local vaults
3dce430 fix: guard the star prompt behind the display check; gitignore the per-machine sync artifact
77b621e chore: regenerate local integration files from the updated templates
38750db fix: portable generated configs, non-destructive refresh, per-area memory; bump v0.4.17
0b8de26 fix: repair `bedrock view` navigation; harden update path against legacy installs; bump v0.4.16
5e43bf7 feat: add install.sh caveman installer (uv -> pipx -> pip); document in README
0a14bb0 feat: sync warns agent on framework version mismatch at session start; bump v0.4.15
6406812 fix: refresh-system now updates CLAUDE.md on old/legacy headers and regenerates site; bump v0.4.14
c9aaa14 feat: fix bedrock view browser open; eclectic site redesign with TOC, emojis, anchor links, richer color scheme; bump v0.4.13
```
