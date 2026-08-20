# Layout Migration Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give bedrock an ordered, idempotent, version-gated migration chain so a newer release can safely upgrade an existing project's on-disk layout, and an older release can never silently downgrade it.

**Architecture:** A new `runtime/migrations.py` owns `LAYOUT_VERSION` (an integer bumped only when the on-disk format changes) and an ordered list of one-shot migrations. `bedrock/STATUS.md` records the project's `layout_version` in its frontmatter. `run_refresh()` reads it and branches three ways: recorded < installed runs the pending migrations then stamps; equal proceeds to the normal template refresh; recorded > installed warns and writes nothing, exiting 0 so the SessionStart hook never degrades a session.

**Tech Stack:** Python 3.9+, click, pytest. No new dependencies.

---

## Scope

This plan covers **only** the migration mechanism, plus porting the one existing repair that is genuinely a one-shot migration. It deliberately introduces no new on-disk format beyond the additive `layout_version` key.

A correction to earlier framing: of the three repairs written in the 0.4.17 work, only `_localize_real_path` is a one-shot migration. Hook-command rewriting and `.gitignore` reconciliation must stay **unconditional refresh steps** — they need to re-run every session as templates and pattern lists evolve, so converting them to versioned one-shots would silently stop them from firing. They stay where they are.

The `.state.json` split, per-author event shards, `whoami`, debt capture, and the ignored-but-tracked doctor check are **out of scope** and get their own plan. This plan's value is that it makes those safe to ship.

## File Structure

- **Create `src/agent_knowledge/runtime/migrations.py`** — the registry. Owns `LAYOUT_VERSION`, the `Migration` record, the ordered `MIGRATIONS` tuple, `read_layout_version()`, `stamp_layout_version()`, and `run_migrations()`. Knows nothing about templates or integrations.
- **Modify `src/agent_knowledge/runtime/refresh.py`** — `run_refresh()` gains the version branch and calls `run_migrations()`. `_localize_real_path` moves out to `migrations.py`; its call site inside `_refresh_project_yaml` is removed.
- **Modify `src/agent_knowledge/cli.py`** — `refresh-system` renders a blocked-by-downgrade result; `doctor` reports the layout version.
- **Test `tests/test_migrations.py`** — new file, unit-level, no subprocess. Fast by design: the existing suite is 31 minutes because every behavioral test shells out to `init`, and this plan must not make that worse.
- **Modify `tests/test_cli.py`** — two behavioral tests only, for the refresh-system exit contract.

---

### Task 1: Layout version read and write

**Files:**
- Create: `src/agent_knowledge/runtime/migrations.py`
- Test: `tests/test_migrations.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Verify the layout migration registry: versioning, ordering, idempotence."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_knowledge.runtime import migrations


def _vault(tmp_path: Path, *, layout: str | None = None) -> Path:
    """A minimal repo with a bedrock/STATUS.md, optionally carrying a layout_version."""
    repo = tmp_path / "repo"
    (repo / "bedrock").mkdir(parents=True)
    lines = ["---", "note_type: knowledge-status", "project: demo"]
    if layout is not None:
        lines.append(f"layout_version: {layout}")
    lines += ["---", "", "# Status", ""]
    (repo / "bedrock" / "STATUS.md").write_text("\n".join(lines), encoding="utf-8")
    return repo


def test_missing_layout_version_reads_as_zero(tmp_path: Path):
    """A vault predating the registry is layout 0, so every migration is pending."""
    assert migrations.read_layout_version(_vault(tmp_path)) == 0


def test_layout_version_round_trips(tmp_path: Path):
    """Stamping then reading must return what was written."""
    repo = _vault(tmp_path)
    migrations.stamp_layout_version(repo, 3, dry_run=False)
    assert migrations.read_layout_version(repo) == 3


def test_stamp_is_a_no_op_under_dry_run(tmp_path: Path):
    """--dry-run must not touch STATUS.md."""
    repo = _vault(tmp_path, layout="1")
    migrations.stamp_layout_version(repo, 9, dry_run=True)
    assert migrations.read_layout_version(repo) == 1


def test_unparsable_layout_version_reads_as_zero(tmp_path: Path):
    """A hand-mangled value must degrade to 'migrate me', never crash the hook."""
    assert migrations.read_layout_version(_vault(tmp_path, layout="not-a-number")) == 0


def test_missing_status_file_reads_as_zero(tmp_path: Path):
    """An uninitialized repo must not raise."""
    repo = tmp_path / "empty"
    repo.mkdir()
    assert migrations.read_layout_version(repo) == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_migrations.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agent_knowledge.runtime.migrations'`

- [ ] **Step 3: Write the minimal implementation**

```python
"""Ordered, idempotent migrations for the on-disk vault layout.

The package version and the layout version are deliberately separate. Most
releases change no on-disk format and leave LAYOUT_VERSION alone; bumping it is
an explicit act that says "an existing project needs work done to it".
"""

from __future__ import annotations

import re
from pathlib import Path

# Bump only when the on-disk layout changes, and add a Migration for it.
LAYOUT_VERSION = 1


def _status_path(repo_root: Path) -> Path:
    return repo_root / "bedrock" / "STATUS.md"


def read_layout_version(repo_root: Path) -> int:
    """The project's recorded layout version, or 0 when absent or unreadable.

    Degrading to 0 rather than raising matters: this runs from the SessionStart
    hook, where an exception would surface as a broken agent session.
    """
    try:
        text = _status_path(repo_root).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0
    m = re.search(r"^layout_version:\s*(.+)$", text, re.MULTILINE)
    if not m:
        return 0
    try:
        return int(m.group(1).strip().strip("\"'"))
    except ValueError:
        return 0


def stamp_layout_version(repo_root: Path, version: int, *, dry_run: bool) -> None:
    """Record the layout version in STATUS.md frontmatter."""
    if dry_run:
        return
    from agent_knowledge.runtime.refresh import _fm_set

    path = _status_path(repo_root)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    path.write_text(_fm_set(text, "layout_version", str(version)), encoding="utf-8")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_migrations.py -v`
Expected: PASS, 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/agent_knowledge/runtime/migrations.py tests/test_migrations.py
git commit -m "feat: record an on-disk layout version separate from the package version"
```

---

### Task 2: The migration registry and runner

**Files:**
- Modify: `src/agent_knowledge/runtime/migrations.py`
- Test: `tests/test_migrations.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_migrations.py`:

```python
def test_pending_returns_only_migrations_above_the_recorded_version(tmp_path: Path):
    """A project at layout 1 must not re-run migration 1."""
    calls = []
    registry = (
        migrations.Migration(1, "first", lambda repo, dry_run: calls.append(1)),
        migrations.Migration(2, "second", lambda repo, dry_run: calls.append(2)),
        migrations.Migration(3, "third", lambda repo, dry_run: calls.append(3)),
    )
    repo = _vault(tmp_path, layout="1")

    applied = migrations.run_migrations(repo, dry_run=False, registry=registry, target=3)

    assert calls == [2, 3], "only migrations above the recorded version may run"
    assert [m.name for m in applied] == ["second", "third"]


def test_migrations_run_in_ascending_order(tmp_path: Path):
    """Order is the whole contract: migration 3 may depend on 2 having run."""
    calls = []
    registry = (
        migrations.Migration(3, "third", lambda repo, dry_run: calls.append(3)),
        migrations.Migration(1, "first", lambda repo, dry_run: calls.append(1)),
        migrations.Migration(2, "second", lambda repo, dry_run: calls.append(2)),
    )

    migrations.run_migrations(_vault(tmp_path), dry_run=False, registry=registry, target=3)

    assert calls == [1, 2, 3]


def test_runner_stamps_the_target_version(tmp_path: Path):
    """After migrating, the project must not migrate again on the next session."""
    registry = (migrations.Migration(1, "first", lambda repo, dry_run: None),)
    repo = _vault(tmp_path)

    migrations.run_migrations(repo, dry_run=False, registry=registry, target=1)

    assert migrations.read_layout_version(repo) == 1


def test_dry_run_neither_applies_nor_stamps(tmp_path: Path):
    """--dry-run must report the plan without touching the vault."""
    calls = []
    registry = (migrations.Migration(1, "first", lambda repo, dry_run: calls.append(dry_run)),)
    repo = _vault(tmp_path)

    applied = migrations.run_migrations(repo, dry_run=True, registry=registry, target=1)

    assert [m.name for m in applied] == ["first"], "the plan must still be reported"
    assert calls == [True], "the migration must be told it is a dry run"
    assert migrations.read_layout_version(repo) == 0, "dry-run must not stamp"


def test_up_to_date_project_runs_nothing(tmp_path: Path):
    """The common case: no work, no write."""
    calls = []
    registry = (migrations.Migration(1, "first", lambda repo, dry_run: calls.append(1)),)
    repo = _vault(tmp_path, layout="1")

    assert migrations.run_migrations(repo, dry_run=False, registry=registry, target=1) == []
    assert calls == []


```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_migrations.py -v`
Expected: FAIL — `AttributeError: module 'agent_knowledge.runtime.migrations' has no attribute 'Migration'`

- [ ] **Step 3: Write the minimal implementation**

Add to `src/agent_knowledge/runtime/migrations.py`, after the imports:

```python
from typing import Callable, NamedTuple, Sequence


class Migration(NamedTuple):
    """One irreversible step from layout `version - 1` to `version`.

    `apply` must be idempotent: it runs from the SessionStart hook, and a crash
    partway through a chain leaves the stamp unwritten, so the whole chain
    re-runs on the next session.
    """

    version: int
    name: str
    apply: Callable[[Path, bool], None]
```

and, after `stamp_layout_version`:

```python
def run_migrations(
    repo_root: Path,
    *,
    dry_run: bool,
    registry: Sequence[Migration] | None = None,
    target: int | None = None,
) -> list[Migration]:
    """Apply every migration above the project's recorded version, in order.

    Returns the migrations that were applied (or, under dry_run, would be).
    `registry` and `target` are injectable so the ordering contract can be
    tested without inventing real layout versions.
    """
    registry = MIGRATIONS if registry is None else registry
    target = LAYOUT_VERSION if target is None else target

    current = read_layout_version(repo_root)
    pending = sorted(
        (m for m in registry if current < m.version <= target),
        key=lambda m: m.version,
    )
    if not pending:
        return []

    for migration in pending:
        migration.apply(repo_root, dry_run)

    stamp_layout_version(repo_root, target, dry_run=dry_run)
    return pending
```

and at the end of the file:

```python
MIGRATIONS: tuple[Migration, ...] = ()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_migrations.py -v`
Expected: PASS, 10 passed

- [ ] **Step 5: Commit**

```bash
git add src/agent_knowledge/runtime/migrations.py tests/test_migrations.py
git commit -m "feat: add an ordered idempotent migration runner"
```

---

### Task 3: Port real_path localization to migration 1

**Files:**
- Modify: `src/agent_knowledge/runtime/migrations.py`
- Modify: `src/agent_knowledge/runtime/refresh.py:456-500` (remove `_localize_real_path` and its call site in `_refresh_project_yaml`)
- Test: `tests/test_migrations.py`, `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_migrations.py`:

```python
def test_migration_1_localizes_an_absolute_real_path(tmp_path: Path):
    """The 0.4.17 repair becomes layout migration 1."""
    repo = _vault(tmp_path)
    project_yaml = repo / ".agent-project.yaml"
    project_yaml.write_text(
        "knowledge:\n"
        "  vault_mode: local\n"
        "  real_path: /home/someone/code/proj/bedrock\n"
        "  ignore_file: ./.agentknowledgeignore\n",
        encoding="utf-8",
    )

    migrations.run_migrations(repo, dry_run=False)

    text = project_yaml.read_text()
    assert "real_path: ./bedrock" in text
    assert "ignore_file: ./.agentknowledgeignore" in text, "neighbouring keys must survive"
    assert migrations.read_layout_version(repo) == migrations.LAYOUT_VERSION


def test_migration_1_leaves_an_external_vault_alone(tmp_path: Path):
    """An external vault legitimately points outside the repo."""
    repo = _vault(tmp_path)
    project_yaml = repo / ".agent-project.yaml"
    original = "knowledge:\n  vault_mode: external\n  real_path: /home/me/agent-os/projects/x\n"
    project_yaml.write_text(original, encoding="utf-8")

    migrations.run_migrations(repo, dry_run=False)

    assert project_yaml.read_text() == original


def test_registry_versions_are_unique_and_cover_the_layout_version():
    """A duplicate or skipped version silently breaks ordering."""
    versions = [m.version for m in migrations.MIGRATIONS]
    assert versions == sorted(set(versions)), "versions must be unique and ordered"
    assert versions == list(range(1, migrations.LAYOUT_VERSION + 1)), (
        "every layout version from 1 to LAYOUT_VERSION needs exactly one migration"
    )


def test_migration_1_is_idempotent(tmp_path: Path):
    """Re-running the chain on an already-migrated vault must change nothing."""
    repo = _vault(tmp_path)
    project_yaml = repo / ".agent-project.yaml"
    project_yaml.write_text(
        "knowledge:\n  vault_mode: local\n  real_path: /abs/proj/bedrock\n", encoding="utf-8"
    )

    migrations.run_migrations(repo, dry_run=False)
    first = project_yaml.read_text()
    migrations.stamp_layout_version(repo, 0, dry_run=False)  # force a re-run
    migrations.run_migrations(repo, dry_run=False)

    assert project_yaml.read_text() == first
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_migrations.py -v -k migration_1`
Expected: FAIL — `assert 'real_path: ./bedrock' in ...`, since `MIGRATIONS` is still empty.

- [ ] **Step 3: Move the implementation**

Cut `_localize_real_path` from `refresh.py` and paste it into `migrations.py` as a module-level function named `_localize_real_path`, unchanged. Then add the migration and register it:

```python
def _migrate_real_path_to_relative(repo_root: Path, dry_run: bool) -> None:
    """Layout 1: `.agent-project.yaml` records real_path relatively for local vaults.

    An absolute path only records which machine generated the file and breaks
    every other clone.
    """
    target = repo_root / ".agent-project.yaml"
    try:
        current = target.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    updated, localized = _localize_real_path(current)
    if localized and not dry_run:
        target.write_text(updated, encoding="utf-8")


MIGRATIONS: tuple[Migration, ...] = (
    Migration(1, "real_path -> ./bedrock (portable across machines)", _migrate_real_path_to_relative),
)
```

In `refresh.py`, delete the now-dead `_localize_real_path` and simplify `_refresh_project_yaml` so it only manages `framework_version`:

```python
def _refresh_project_yaml(repo_root: Path, version: str, *, dry_run: bool) -> dict[str, Any]:
    """Update framework_version in .agent-project.yaml. Layout repairs are migrations."""
    target = repo_root / ".agent-project.yaml"

    if not target.is_file():
        return {"target": ".agent-project.yaml", "action": "skip", "detail": "file not found"}

    current = target.read_text(encoding="utf-8", errors="replace")
    prior = ""
    m = re.search(r'^framework_version:\s*(.+)$', current, re.MULTILINE)
    if m:
        prior = m.group(1).strip().strip("\"'")

    if prior == version:
        return {"target": ".agent-project.yaml", "action": "up-to-date", "detail": f"framework_version already {version}"}

    action = _write(target, _yaml_set(current, "framework_version", version), dry_run=dry_run)
    detail = f"set framework_version: {version}" + (f" (was: {prior})" if prior else "")
    return {"target": ".agent-project.yaml", "action": action, "detail": detail}
```

- [ ] **Step 4: Update the tests that imported the moved function**

In `tests/test_cli.py`, the four `_localize_real_path` tests import from `agent_knowledge.runtime.refresh`. Change each import to `from agent_knowledge.runtime.migrations import _localize_real_path`. The test bodies do not change. Also update `test_refresh_system_localizes_real_path` — it drives the CLI end to end and must still pass unchanged, because `run_refresh` now reaches the same behaviour through the migration chain.

- [ ] **Step 5: Run the full unit tests plus the affected CLI tests**

Run: `python3 -m pytest tests/test_migrations.py -v && python3 -m pytest tests/test_cli.py -k "localize or real_path" -v`
Expected: PASS — all migration tests including `test_registry_versions_are_unique_and_cover_the_layout_version`, which now sees `MIGRATIONS` covering version 1.

- [ ] **Step 6: Commit**

```bash
git add src/agent_knowledge/runtime/migrations.py src/agent_knowledge/runtime/refresh.py tests/test_migrations.py tests/test_cli.py
git commit -m "refactor: move real_path localization into layout migration 1"
```

---

### Task 4: Wire migrations into refresh, with the downgrade guard

**Files:**
- Modify: `src/agent_knowledge/runtime/refresh.py` (`run_refresh`)
- Test: `tests/test_migrations.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_migrations.py`:

```python
def test_refresh_refuses_to_downgrade_a_newer_project(tmp_path: Path):
    """An older CLI must never rewrite a newer project's files.

    refresh-system runs from the SessionStart hook, so without this a teammate
    on an older bedrock silently reverts the layout on every session.
    """
    from agent_knowledge.runtime.refresh import run_refresh

    repo = _vault(tmp_path, layout=str(migrations.LAYOUT_VERSION + 1))
    (repo / ".agent-project.yaml").write_text("framework_version: \"0.0.1\"\n", encoding="utf-8")

    result = run_refresh(repo, dry_run=False)

    assert result["action"] == "blocked"
    assert result["layout_version"] == migrations.LAYOUT_VERSION
    assert result["project_layout_version"] == migrations.LAYOUT_VERSION + 1
    assert any("pip install -U project-bedrock" in w for w in result["warnings"])
    assert "0.0.1" in (repo / ".agent-project.yaml").read_text(), (
        "a blocked refresh must write nothing at all"
    )


def test_refresh_reports_applied_migrations(tmp_path: Path):
    """Migrations show up as changes so the user can see what happened."""
    from agent_knowledge.runtime.refresh import run_refresh

    repo = _vault(tmp_path)
    (repo / ".agent-project.yaml").write_text(
        "knowledge:\n  vault_mode: local\n  real_path: /abs/proj/bedrock\n", encoding="utf-8"
    )

    result = run_refresh(repo, dry_run=False)

    targets = [c["target"] for c in result["changes"]]
    assert "layout migration" in targets
    assert migrations.read_layout_version(repo) == migrations.LAYOUT_VERSION
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_migrations.py -v -k "downgrade or applied_migrations"`
Expected: FAIL — `KeyError: 'layout_version'`, since `run_refresh` does not yet return those keys.

- [ ] **Step 3: Write the implementation**

In `refresh.py`, add the import at the top of `run_refresh`:

```python
    from agent_knowledge.runtime.integrations import detect
    from agent_knowledge.runtime.migrations import LAYOUT_VERSION, read_layout_version, run_migrations
```

Immediately after `prior_version` is computed and before `changes: list[dict[str, Any]] = []` is used, insert the guard and the migration step:

```python
    project_layout = read_layout_version(repo_root)

    changes: list[dict[str, Any]] = []
    warnings: list[str] = []

    if project_layout > LAYOUT_VERSION:
        # Never write: an older CLI would revert a newer project's layout, and
        # this runs from SessionStart, so it would happen on every session.
        warnings.append(
            f"This project uses bedrock layout {project_layout}; this install understands "
            f"{LAYOUT_VERSION}. Run: pip install -U project-bedrock"
        )
        return {
            "action": "blocked",
            "framework_version": version,
            "prior_version": prior_version,
            "layout_version": LAYOUT_VERSION,
            "project_layout_version": project_layout,
            "dry_run": dry_run,
            "integrations_detected": [k for k, v in detected.items() if v],
            "changes": [],
            "warnings": warnings,
        }

    for applied in run_migrations(repo_root, dry_run=dry_run):
        changes.append({
            "target": "layout migration",
            "action": "dry-run" if dry_run else "updated",
            "detail": f"{applied.version}: {applied.name}",
        })
```

Delete the now-duplicated `changes`/`warnings` initialisation further down. Add both version keys to the returned dict at the end of the function:

```python
    return {
        "action": action,
        "framework_version": version,
        "prior_version": prior_version,
        "layout_version": LAYOUT_VERSION,
        "project_layout_version": max(project_layout, LAYOUT_VERSION),
        "dry_run": dry_run,
        "integrations_detected": [k for k, v in detected.items() if v],
        "changes": changes,
        "warnings": warnings,
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_migrations.py -v`
Expected: PASS, all 16 tests

- [ ] **Step 5: Commit**

```bash
git add src/agent_knowledge/runtime/refresh.py tests/test_migrations.py
git commit -m "feat: run layout migrations from refresh-system and refuse to downgrade"
```

---

### Task 5: The CLI must warn without failing the session

**Files:**
- Modify: `src/agent_knowledge/cli.py:1104-1140` (the `refresh_system` output block)
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli.py`:

```python
def test_refresh_system_exits_zero_when_blocked_by_a_newer_layout(tmp_path: Path):
    """A blocked refresh must warn and exit 0.

    It runs from the SessionStart hook: a non-zero exit there degrades every
    agent session in the repo, which is worse than the stale layout it reports.
    """
    from agent_knowledge.runtime.migrations import LAYOUT_VERSION

    repo = _init_repo(tmp_path, "layout-newer")
    kh = tmp_path / "kh"
    _run("init", "--repo", str(repo), "--knowledge-home", str(kh))

    status = repo / "bedrock" / "STATUS.md"
    status.write_text(
        status.read_text().replace(
            f"layout_version: {LAYOUT_VERSION}", f"layout_version: {LAYOUT_VERSION + 1}"
        ),
        encoding="utf-8",
    )

    r = _run("refresh-system", "--project", str(repo))

    assert r.returncode == 0, "a blocked refresh must not fail the SessionStart hook"
    assert "pip install -U project-bedrock" in r.stderr
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m pytest tests/test_cli.py -k blocked_by_a_newer_layout -v`
Expected: FAIL — the command prints `Refreshed to v...` rather than the upgrade hint, so the stderr assertion fails.

- [ ] **Step 3: Write the implementation**

In `cli.py`, in `refresh_system`, immediately after `result = run_refresh(...)` and the `json_mode` early return, insert:

```python
    if result["action"] == "blocked":
        for w in result.get("warnings", []):
            click.secho(f"Warning: {w}", fg="yellow", err=True)
        click.echo("", err=True)
        click.echo("No files were changed.", err=True)
        return  # exit 0: this runs from SessionStart and must not break the session
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m pytest tests/test_cli.py -k blocked_by_a_newer_layout -v`
Expected: PASS

- [ ] **Step 5: Report the layout version in doctor**

In `cli.py`, in the `doctor` command's non-JSON output, after the framework-version staleness block, add:

```python
    from agent_knowledge.runtime.migrations import LAYOUT_VERSION, read_layout_version

    project_layout = read_layout_version(repo_root)
    if project_layout > LAYOUT_VERSION:
        click.secho(
            f"Warning: project layout {project_layout} is newer than this install "
            f"({LAYOUT_VERSION}). Run: pip install -U project-bedrock",
            fg="yellow",
            err=True,
        )
    elif project_layout < LAYOUT_VERSION:
        click.secho(
            f"Warning: project layout {project_layout} is behind this install "
            f"({LAYOUT_VERSION}). Run: bedrock refresh-system",
            fg="yellow",
            err=True,
        )
```

- [ ] **Step 6: Run the whole suite**

Run: `python3 -m pytest tests/ -q`
Expected: PASS. The suite takes roughly 31 minutes; run it in the background and check the result rather than blocking on it.

- [ ] **Step 7: Commit**

```bash
git add src/agent_knowledge/cli.py tests/test_cli.py
git commit -m "feat: report layout version in doctor; blocked refresh warns without failing"
```

---

### Task 6: Document the layout contract

**Files:**
- Modify: `docs/reference.md` (the "Keeping up to date" section)

- [ ] **Step 1: Add the section**

After the existing "One-time fix for projects set up before 0.4.17" block, add:

```markdown
### Layout versions

`bedrock/STATUS.md` records a `layout_version` — an integer describing the
on-disk shape of the vault, separate from `framework_version`. Most releases
change no layout and leave it alone.

- **Your install is newer than the project:** `refresh-system` applies the
  pending migrations in order and stamps the new version. This happens
  automatically from the `SessionStart` hook.
- **Your install is older than the project:** `refresh-system` writes nothing
  and tells you to upgrade. Without this, an older teammate would revert the
  layout on every session, and the newer teammate would restore it — forever.

`bedrock doctor` reports which side you are on. Migrations only ever move data;
nothing is deleted, so `refresh-system --dry-run` is safe to inspect first.
```

- [ ] **Step 2: Commit**

```bash
git add docs/reference.md
git commit -m "docs: explain layout versions and the no-downgrade rule"
```

---

## Verification

Before calling this done:

- [ ] `python3 -m pytest tests/ -q` passes locally (~31 min; run in the background)
- [ ] `bedrock refresh-system --project .` on this repo reports `layout migration` once, then reports nothing on a second run
- [ ] `bedrock doctor --project .` prints no layout warning afterwards
- [ ] CI is green on all 8 matrix jobs before merging

## What this deliberately does not do

- No `.state.json` split, event sharding, `whoami`, debt capture, or ignored-but-tracked doctor check. Those are the next plan, and each becomes migration 2, 3, … on top of this mechanism.
- No change to hook-command rewriting or `.gitignore` reconciliation. Both must keep running unconditionally on every session, so neither is a one-shot migration.
