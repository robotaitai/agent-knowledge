<div align="center">

<img src="docs/cover.png" width="100%" alt="project-bedrock cover" />

# project-bedrock: A project cockpit for your AI agents.

### Every session starts with context.  
### Every important decision leaves a trail.  
### Every session leaves the project smarter.

robotaitai

[![PyPI](https://img.shields.io/pypi/v/project-bedrock?color=blue&label=PyPI)](https://pypi.org/project/project-bedrock/)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-ready-orange)](https://docs.anthropic.com/en/docs/claude-code)
[![Cursor](https://img.shields.io/badge/Cursor-ready-purple)](https://cursor.sh) 
[![Codex](https://img.shields.io/badge/Codex-ready-black)](https://openai.com/codex) 
[![License: MIT](https://img.shields.io/badge/License-MIT-green)](LICENSE) 

<img src="docs/demo.gif" width="100%" alt="project-bedrock demo" />

</div>

---

AI can write code fast.

What it does **not** do well by default is leave behind clear, shared project understanding.

Decisions disappear into chat history.  
Architecture gets rediscovered.  
New sessions start from zero.  
And the next developer, human or AI, has to figure out again what changed, where, and why.

**Project Bedrock** turns your repo into a project cockpit for AI agents:
what we know, what matters now, and what to load next.

It works like the operating discipline of a strong team lead:
- every session starts with context
- every important change leaves a trail
- stable knowledge gets written down where the next developer can find it
- the project becomes easier to understand over time, not harder

With one command, your project gets:
- PROJECT-SHAPED MEMORY for architecture, decisions, conventions, and domain context
- A SMALL WORK LAYER for current focus, open loops, and recommended next actions
- PROJECT-LOCAL integration for **Claude Code**, **Cursor**, and **Codex**
- lightweight git-friendly markdown that LIVES WITH THE REPO
- HTML, graph, and Obsidian-ready VIEWS for human inspection

Under the hood, it is just markdown files and a CLI.  
No database. No server. No hosted backend. No black box.

**The result:** your AI developers stop behaving like disconnected sessions, and start behaving more like a team.

## 📦 Install

**Option A — let your agent do it** (no pip knowledge needed):

Paste this into Claude Code, Cursor, or any capable agent:

```
Install the `project-bedrock` CLI on this machine so `bedrock --version` works. Handle Python and pipx installation if missing. Fix any errors along the way. Don't stop until it's working.
```

The agent detects your OS, installs Python + pipx if needed, installs the package, and verifies it. Works on macOS, Linux, and Windows.

**Option B — one-liner (Mac / Linux):**

```bash
curl -fsSL https://raw.githubusercontent.com/robotaitai/project-bedrock/main/install.sh | bash
```

Auto-detects **uv** → **pipx** → **pip** in that order.

**Option C — pick your tool:**

```bash
uv tool install project-bedrock   # fastest, isolated (recommended)
pipx install project-bedrock      # isolated
pip install project-bedrock       # classic
```

> **PyPI:** `project-bedrock` &nbsp;&middot;&nbsp; **CLI:** `bedrock` &nbsp;&middot;&nbsp; **alias:** `agent-knowledge` (deprecated)

---

## 🚀 Quick Start

**1. Initialize the project** (run once in your project folder):

```bash
cd your-project
bedrock init
```

**2. Onboard your agent** — paste this into chat:

```
Read AGENTS.md and ./bedrock/STATUS.md, then onboard this project.
```

**That's it.** The agent writes stable knowledge into `Memory/`, current priorities into `Work/`, and every future session starts with better context automatically.

<details>
<summary><b>What <code>init</code> does in one shot</b></summary>

<br>

| Step | What happens |
|------|-------------|
| 1 | Creates `./bedrock/` as a **real directory** inside the repo (git-tracked) |
| 2 | Registers the project in `~/agent-os/projects/<slug>/` so **every project shows up in one place** -- open it in Obsidian for a unified cross-project vault |
| 3 | Adds noisy generated subfolders (`Evidence/raw/`, `Views/site/`, ...) to `.gitignore` automatically |
| 4 | Installs project-local integration for **Claude Code** and **Cursor** |
| 5 | Detects **Codex** and installs its bridge files if present |
| 6 | Bootstraps the project cockpit (`Memory/`, `Work/`, `Views/`) and marks onboarding as `pending` |
| 7 | Imports repo history into `Evidence/` and backfills lightweight history from git |

</details>

---

## 💾 Storage Modes

By default, knowledge lives **inside** the repo (git-tracked).
Curated knowledge is committed normally; noisy subfolders are gitignored.

```bash
# Default: in-repo (recommended)
bedrock init

# External: knowledge outside the repo (not committed)
bedrock init --external

# Convert external -> in-repo later
bedrock migrate-to-local
```

---

## 🧠 How It Works

Think of the vault as your team's **shared project cockpit**. The goal is not more documentation for agents to blindly read. The goal is less context, loaded better.

### Project Cockpit

| | Folder | What goes here | Canon? |
|---|--------|---------------|:------:|
| 📘 | **`Memory/`** | What the project knows -- stable, durable, project-shaped knowledge | **Yes** |
| 🎯 | **`Work/`** | What matters now -- current focus, next actions, open questions, risks | **Yes** |
| 👁️ | **`Views/`** | Human inspection views -- generated site and graph output | No |
| 📅 | `History/` | Legacy diary layer -- still supported | **Yes** |
| 📎 | `Evidence/` | Raw imports: docs, ADRs, PRs, screenshots -- captured context | No |
| 📊 | `Outputs/` | Legacy generated artifacts -- still supported | No |

> **The rule:** stable facts go into `Memory/`, current priorities go into `Work/`, and generated views stay in `Views/`. Imported or generated material is never canon by itself.

### Memory Is Project-Shaped

Bedrock does not force every repo into the same documentation template.

- A robotics repo may organize Memory around `perception/`, `navigation/`, `localization/`, and `safety/`
- A SaaS repo may organize Memory around `frontend/`, `backend/`, `auth/`, `billing/`, and `data/`
- Bedrock itself may organize Memory around `product/`, `runtime/`, `cli/`, `integrations/`, `memory-model/`, and `views/`

### Distinct Minds + Team Consensus

When a team shares one vault in git, you want two things that pull in opposite
directions: each person's own perspective preserved, *and* a single agreed truth.
Bedrock keeps both, as additive folders under `Memory/`:

| | Folder | What goes here | Canon? |
|---|--------|---------------|:------:|
| 👤 | **`Memory/Members/<id>/`** | One folder per member (person **or** agent) -- their own perspective. Each member edits only their folder, so people never collide in git. | No (perspective) |
| 🤝 | **`Memory/Team/`** | Normalized consensus the team converged on through managed dialogue. | **Yes** |

Member folders are committed on purpose -- that is the transparency: a lead can
read each person's stance, and members know their view is recorded and visible.

```bash
bedrock member add "Dana Levi" --role Backend   # scaffold a mind
bedrock member add "Aria" --kind agent          # agents are members too
bedrock member use "Dana Levi"                  # tell bedrock who you are (this machine)
bedrock member whoami                            # resolved: env -> .bedrock/member -> git user
bedrock member list                              # who exists + roles
```

Identity resolves from `BEDROCK_MEMBER`, then `.bedrock/member` (per-machine,
gitignored), then your `git config user.name` -- so in a git-backed vault it
usually just works with no setup.

---

## 🔌 Project-Local Integration

The project carries **everything it needs**. Claude Code, Cursor, and Codex all get integration installed automatically on `init` -- hooks, runtime contracts, and slash commands. No global config.

### Platform & Tool Support

| | ![Claude Code](https://img.shields.io/badge/Claude_Code-black?logo=anthropic) | ![Cursor](https://img.shields.io/badge/Cursor-black?logo=cursor) | ![Codex](https://img.shields.io/badge/Codex-black?logo=openai) |
|:---|:---:|:---:|:---:|
| ![macOS](https://img.shields.io/badge/macOS-silver?logo=apple&logoColor=black) | ![full](https://img.shields.io/badge/full-2ea44f) | ![full](https://img.shields.io/badge/full-2ea44f) | ![bridge](https://img.shields.io/badge/bridge_only-lightgrey) |
| ![Linux](https://img.shields.io/badge/Linux-silver?logo=linux&logoColor=black) | ![full](https://img.shields.io/badge/full-2ea44f) | ![full](https://img.shields.io/badge/full-2ea44f) | ![bridge](https://img.shields.io/badge/bridge_only-lightgrey) |
| ![Windows](https://img.shields.io/badge/Windows-silver?logo=windows&logoColor=0078d4) | ![full](https://img.shields.io/badge/full-2ea44f) | ![full](https://img.shields.io/badge/full-2ea44f) | ![bridge](https://img.shields.io/badge/bridge_only-lightgrey) |

![full](https://img.shields.io/badge/full-2ea44f) &nbsp;Auto-installed on `init` -- hooks fire automatically, slash commands active, `bedrock doctor` validates health. &nbsp;
![bridge](https://img.shields.io/badge/bridge_only-lightgrey) &nbsp;`AGENTS.md` installed when `.codex/` detected -- agent loads memory context, no automated hooks.

> CI matrix: ubuntu-latest + macos-latest, Python 3.9 / 3.10 / 3.12 / 3.13. Windows: Git Bash auto-detected; forward-slash paths and UTF-8 subprocess encoding fixed in v0.4.0.

### 👥 Built For More Than One Developer

Generated hook commands carry **no machine-specific paths**:

```json
"command": "bedrock sync && bedrock refresh-system"
```

The CLI walks up from wherever it was invoked to find the project root. Nothing to hardcode, nothing that breaks when a path contains a space, and nothing that depends on which shell your agent picked -- on Windows, hooks run under Git Bash or PowerShell, and those two disagree about variable expansion.

Everything machine-specific is either relative or gitignored, so `.claude/settings.json` and `.cursor/hooks.json` are safe to commit and a fresh clone works immediately. Projects set up by an older version repair themselves on the next session -- nobody edits generated files by hand.

<details>
<summary><b>Claude Code</b> &nbsp;<code>.claude/</code></summary>

<br>

| File | Purpose |
|------|---------|
| `settings.json` | Lifecycle hooks: sync on SessionStart, Stop, PreCompact |
| `CLAUDE.md` | Runtime contract: knowledge layers, session protocol, onboarding |
| `commands/memory-update.md` | `/memory-update` slash command |
| `commands/system-update.md` | `/system-update` slash command |
| `commands/absorb.md` | `/absorb <file/folder>` slash command |
    
</details>

<details>
<summary><b>Cursor</b> &nbsp;<code>.cursor/</code></summary>

<br>

| File | Purpose |
|------|---------|
| `rules/bedrock.mdc` | Always-on rule: loads memory context on every session |
| `hooks.json` | Lifecycle hooks: sync on start, update on write, sync on stop/compact |
| `commands/memory-update.md` | `/memory-update` slash command |
| `commands/system-update.md` | `/system-update` slash command |
| `commands/absorb.md` | `/absorb <file/folder>` slash command |

</details>

<details>
<summary><b>Codex</b> &nbsp;<code>.codex/</code> &nbsp;(installed when detected)</summary>

<br>

| File | Purpose |
|------|---------|
| `AGENTS.md` | Agent contract with knowledge layer instructions |

</details>

### ⚡ Session Lifecycle

Hooks fire automatically -- **zero manual intervention:**

| Event | Claude Code | Cursor | What runs |
|-------|:-----------:|:------:|-----------|
| Session start | `SessionStart` | `session-start` | `bedrock sync` |
| File saved | -- | `post-write` | `bedrock update` |
| Task complete | `Stop` | `stop` | `bedrock sync` |
| Context compaction | `PreCompact` | `preCompact` | `bedrock sync` |

The agent reads `STATUS.md`, `Memory/PROJECT.md`, and `Work/NOW.md` at the start of every session, with no prompting required.

### 💬 Slash Commands

These are how the team writes to the logbook. Both work in Claude Code and Cursor -- `init` installed them.

| Command | When to use it |
|---------|---------------|
| **`/memory-update`** | End of session, before logging off. The agent updates the project cockpit: stable facts in `Memory/`, current priorities in `Work/`, and a short summary of what changed. |
| **`/system-update`** | After upgrading `project-bedrock`. Refreshes hooks, rules, commands. Purely infrastructure -- never touches knowledge content. |

> A developer should never finish a session without updating the cockpit. The point is not to save everything. The point is to save the next useful context.

### 🩺 Integration Health

```bash
bedrock doctor
```

Reports whether all integration files are installed and current. If anything is stale or missing, `doctor` tells you exactly what to run.

### ⬆️ Upgrades That Can't Go Backwards

`bedrock/STATUS.md` records a `layout_version` describing the on-disk shape of the vault, separate from the package version.

If your install is **newer** than the project, `refresh-system` migrates it forward automatically. If your install is **older**, it writes nothing and tells you to upgrade -- otherwise a teammate on an older version would quietly revert the layout on every session, and the teammate on the newer one would restore it, forever.

A blocked refresh still exits 0, because it runs from a session hook where a hard failure would take the whole session down with it.

---

## 🔮 Obsidian-Ready

Each project's `./bedrock/` is a valid **Obsidian vault** on its own. But the real payoff is `~/agent-os/projects/`: every project you've ever run `init` in is registered there. Open that folder in Obsidian and you have **a unified vault across all your teams' projects** -- backlinks, graph view, and full-text search spanning every codebase you manage.

One window. Every team.

<img src="docs/obsidian-graph.gif" width="100%" alt="Obsidian graph view" />

```bash
bedrock export-canvas
# produces: bedrock/Views/graph/knowledge-export.canvas
```

Obsidian is optional. Works without it too.

---

## 🛠️ Commands

| Command | What it does |
|---------|-------------|
| `init` | Set up a project -- one command, no arguments |
| `sync` | Full sync: memory, history, git evidence, index |
| `ship` | Validate + sync + commit + push |
| `view` | Build the site and open it -- prints the path instead when there is no display, `--serve` to forward a port over SSH |
| `doctor` | Validate setup, integration health, note staleness |
| `member` | Manage per-member context: `add` / `list` / `whoami` / `use` |

<details>
<summary><b>All commands</b></summary>

<br>

`absorb` &middot; `search` &middot; `member` &middot; `export-html` &middot; `export-canvas` &middot; `clean-import` &middot; `refresh-system` &middot; `backfill-history` &middot; `compact` &middot; `migrate-to-local` &middot; `init --external`

All write commands support `--dry-run` and `--json`. Run `bedrock --help` for the full list.

</details>

## More

- [Static site export](docs/reference.md#static-site-export) -- `bedrock view` builds an interactive HTML site from your vault
- [Automatic capture](docs/reference.md#automatic-capture) -- every sync event is recorded as lightweight evidence
- [Progressive retrieval](docs/reference.md#progressive-retrieval) -- agents load only the branches they need
- [Clean web import](docs/reference.md#clean-web-import) -- import a URL as cleaned markdown evidence
- [Project history](docs/reference.md#project-history) -- lightweight event log auto-backfilled from git
- [Keeping up to date](docs/reference.md#keeping-up-to-date) -- `pip install -U project-bedrock` + `bedrock refresh-system`
- [Migrating from agent-knowledge-cli](docs/reference.md#migrating-from-agent-knowledge-cli) -- 3-step migration to `project-bedrock` and the `bedrock` CLI
- [Custom knowledge home](docs/reference.md#custom-knowledge-home) -- change where `~/agent-os/` lives
- [Troubleshooting](docs/reference.md#troubleshooting) -- common issues and fixes
- [Platform support](docs/reference.md#platform-support) -- macOS, Linux, Windows, Python 3.9+
- [Development](docs/reference.md#development) -- contributing and running tests

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=robotaitai/project-bedrock&type=Date)](https://star-history.com/#robotaitai/project-bedrock&Date)
