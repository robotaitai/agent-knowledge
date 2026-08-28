# Proposal: Per-Member Context ("minds") + Team Consensus

Status: implemented (initial cut)
Date: 2026-06-04

## Problem

Project Bedrock stores project knowledge as shared markdown in `Memory/`. When a
vault lives in git and a *team* works against it, two things are missing:

1. **Merge conflicts.** Multiple people curating the same shared notes collide in
   git.
2. **Lost perspective.** Different teammates (and different agents) reason
   differently. Flattening everyone into one shared voice erases that — yet a team
   lead often *wants* to see each person's stance, and teammates benefit from
   knowing their view is recorded and visible.

In practice a team lead drives a *managed dialogue*: individual positions get
surfaced, disagreements get normalized, and the group converges on shared
agreements. The vault should model both ends of that — the distinct "minds" and
the consensus they produce.

## Design

Two additive folders under `Memory/`, orthogonal to the existing by-purpose
layers (Memory/History/Evidence/...):

```
bedrock/Memory/
├─ Team/                 shared, normalized CONSENSUS (canonical team truth)
│  └─ Team.md            branch entry note (frontmatter'd; passes validate)
├─ Members/              one folder per member — distinct "minds"
│  ├─ Members.md         branch entry note (frontmatter'd; passes validate)
│  └─ <member-id>/
│     ├─ PROFILE.md      who they are, role, perspective
│     └─ notes.md        their own context (conflict-free: only they edit it)
└─ <legacy notes...>     existing Memory/*.md still resolve unchanged
```

Each direct subfolder of `Memory/` is a bedrock "branch" that needs a same-name,
frontmatter'd entry note (`<branch>/<branch>.md`), so the scaffold writes
`Team/Team.md` and `Members/Members.md` (not READMEs) to stay clean under
`bedrock validate` and `bedrock doctor`.

- **`Members/<id>/`** is each member's own perspective. Because each person edits
  only their own folder, git merge conflicts between people disappear. Members are
  committed (not per-machine) — that *is* the transparency: a manager can read
  each member's stance, and members know their view is legible upward and outward.
- **`Team/`** holds the normalized consensus that the managed dialogue produces.
  This is canonical truth, same trust level as `Memory/` itself.
- A member may be a **person or an agent** (`kind: person | agent`).

### Identity ("who am I")

So notes attribute to the right member without per-command flags, the current
member is resolved by precedence:

1. `BEDROCK_MEMBER` environment variable
2. `.bedrock/member` file (per-machine, gitignored — set via `bedrock member use`)
3. slug of `git config user.name` (the vault now lives in git, so git already
   knows who each teammate is)
4. unset

Only the *pointer* to the current member (`.bedrock/`) is per-machine and
gitignored. The member folders themselves are shared.

### CLI

```
bedrock member add <name> [--role TEXT] [--kind person|agent]  # scaffold a mind
bedrock member list                                            # who exists + roles
bedrock member whoami                                          # resolved current member
bedrock member use <name>                                      # set current member (this machine)
```

`bedrock bootstrap` also ensures `Memory/Team/` and `Memory/Members/` exist so new
vaults get the structure. Everything is additive and backward compatible: existing
vaults without these folders keep working, and the folders are created on demand.

## Out of scope (future)

- A `member promote <note>` flow to move a member note into `Team/` consensus with
  provenance (models the dialogue → agreement step in the tool itself).
- Per-member views in the generated HTML site / knowledge graph.
- Sync attribution (stamping `author:` automatically from the resolved member).
