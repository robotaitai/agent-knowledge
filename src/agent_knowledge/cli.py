"""CLI entry point for agent-knowledge."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import click

from agent_knowledge import __version__
from agent_knowledge.runtime.paths import get_assets_dir
from agent_knowledge.runtime.shell import run_bash_script, run_python_script


def _add_common_flags(
    args: list[str],
    *,
    dry_run: bool = False,
    json_mode: bool = False,
    force: bool = False,
) -> list[str]:
    if dry_run:
        args.append("--dry-run")
    if json_mode:
        args.append("--json")
    if force:
        args.append("--force")
    return args


@click.group()
@click.version_option(version=__version__, prog_name="agent-knowledge")
def main() -> None:
    """Adaptive, file-based project knowledge for AI coding agents."""


# -- init ------------------------------------------------------------------ #


@main.command()
@click.option("--slug", default=None, help="Project slug (default: repo directory name).")
@click.option("--repo", default=".", type=click.Path(exists=True), help="Project repo path (default: cwd).")
@click.option("--knowledge-home", default=None, help="Knowledge root (default: $AGENT_KNOWLEDGE_HOME or ~/agent-os/projects).")
@click.option("--real-path", default=None, help="Explicit external knowledge folder path.")
@click.option("--no-integrations", is_flag=True, help="Skip auto-detection and installation of tool integrations.")
@click.option("--dry-run", is_flag=True, help="Preview changes without writing.")
@click.option("--json", "json_mode", is_flag=True, help="Output JSON only.")
@click.option("--force", is_flag=True, help="Overwrite existing files.")
def init(
    slug: str | None,
    repo: str,
    knowledge_home: str | None,
    real_path: str | None,
    no_integrations: bool,
    dry_run: bool,
    json_mode: bool,
    force: bool,
) -> None:
    """Initialize a project: create knowledge folder, pointer, and metadata.

    When run with no arguments inside a repo, infers slug from the directory
    name, auto-detects tool integrations, and installs everything needed.
    """
    from agent_knowledge.runtime.integrations import detect, install_all

    repo_path = Path(repo).resolve()
    if slug is None:
        slug = _sanitize_slug(repo_path.name)

    if knowledge_home is None:
        knowledge_home = os.environ.get("AGENT_KNOWLEDGE_HOME")

    # Core setup: symlink, .agent-project.yaml, AGENTS.md, bootstrap
    args = ["--slug", slug, "--repo", str(repo_path)]
    if knowledge_home:
        args.extend(["--knowledge-home", knowledge_home])
    if real_path:
        args.extend(["--real-path", real_path])
    args.append("--install-hooks")
    _add_common_flags(args, dry_run=dry_run, json_mode=json_mode, force=force)
    rc = run_bash_script("install-project-links.sh", args)
    if rc != 0:
        sys.exit(rc)

    # Auto-detect and install tool integrations
    if not no_integrations:
        detected = detect(repo_path)
        if not json_mode:
            tools_found = [t for t, v in detected.items() if v]
            click.echo("", err=True)
            click.echo(f"Detected integrations: {', '.join(tools_found) if tools_found else 'none'}", err=True)

        results = install_all(repo_path, detected, dry_run=dry_run, force=force)
        if not json_mode:
            for tool, actions in results.items():
                click.echo(f"  [{tool}]", err=True)
                for action in actions:
                    click.echo(action, err=True)

    if not json_mode:
        prompt = "Read AGENTS.md and ./agent-knowledge/STATUS.md, then onboard this project."
        border = "+" + "-" * (len(prompt) + 2) + "+"
        click.echo("", err=True)
        click.secho("Ready. Open your agent and send:", bold=True, err=True)
        click.echo("", err=True)
        click.secho(border, fg="cyan", err=True)
        click.secho(f"| {prompt} |", fg="cyan", bold=True, err=True)
        click.secho(border, fg="cyan", err=True)
        click.echo("", err=True)


def _sanitize_slug(name: str) -> str:
    """Normalize a directory name into a safe project slug."""
    import re
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


# -- sync ------------------------------------------------------------------ #


@main.command()
@click.option("--project", default=".", type=click.Path(exists=True), help="Project repo root.")
@click.option("--dry-run", is_flag=True, help="Preview changes without writing.")
@click.option("--json", "json_mode", is_flag=True, help="Output JSON only.")
def sync(project: str, dry_run: bool, json_mode: bool) -> None:
    """Sync memory branches, roll up sessions, and extract git evidence.

    \b
    Steps:
      1. Copy agent_docs/memory/*.md -> agent-knowledge/Memory/ (newer only)
      2. Scan Sessions/ and rebuild Dashboards/session-rollup.md
      3. Extract recent git log into Evidence/raw/git-recent.md
      4. Update last_project_sync in STATUS.md
    """
    import json as json_mod

    from agent_knowledge.runtime.sync import run_sync

    repo_path = Path(project).resolve()
    results = run_sync(repo_path, dry_run=dry_run)

    if json_mode:
        click.echo(json_mod.dumps({"sync": results}, indent=2))
    else:
        for step, actions in results.items():
            click.echo(f"[{step}]", err=True)
            for action in actions:
                click.echo(action, err=True)
            click.echo("", err=True)

        if dry_run:
            click.echo("(dry-run -- no changes written)", err=True)
        else:
            click.secho("Sync complete.", bold=True, err=True)


# -- bootstrap ------------------------------------------------------------- #


@main.command()
@click.option("--project", default=".", type=click.Path(exists=True), help="Project repo root.")
@click.option("--profile", default=None, help="Force a profile (web-app, robotics, ml-platform, hybrid).")
@click.option("--dry-run", is_flag=True, help="Preview changes without writing.")
@click.option("--json", "json_mode", is_flag=True, help="Output JSON only.")
@click.option("--force", is_flag=True, help="Overwrite existing files.")
def bootstrap(
    project: str,
    profile: str | None,
    dry_run: bool,
    json_mode: bool,
    force: bool,
) -> None:
    """Bootstrap or repair the project memory tree."""
    args = ["--project", project]
    if profile:
        args.extend(["--profile", profile])
    _add_common_flags(args, dry_run=dry_run, json_mode=json_mode, force=force)
    sys.exit(run_bash_script("bootstrap-memory-tree.sh", args))


# -- import ---------------------------------------------------------------- #


@main.command(name="import")
@click.option("--project", default=".", type=click.Path(exists=True), help="Project repo root.")
@click.option("--dry-run", is_flag=True, help="Preview changes without writing.")
@click.option("--json", "json_mode", is_flag=True, help="Output JSON only.")
def import_cmd(project: str, dry_run: bool, json_mode: bool) -> None:
    """Import repo history and evidence into Evidence/."""
    args = ["--project", project]
    _add_common_flags(args, dry_run=dry_run, json_mode=json_mode)
    sys.exit(run_bash_script("import-agent-history.sh", args))


# -- update ---------------------------------------------------------------- #


@main.command()
@click.option("--project", default=".", type=click.Path(exists=True), help="Project repo root.")
@click.option("--compact", is_flag=True, help="Run memory compaction after sync.")
@click.option("--decision-title", default=None, help="Record a decision note with this title.")
@click.option("--decision-why", default=None, help="Reason for the decision.")
@click.option("--decision-slug", default=None, help="Custom slug for the decision note.")
@click.option("--summary-file", default=None, hidden=True, help="Write JSON summary to file.")
@click.option("--dry-run", is_flag=True, help="Preview changes without writing.")
@click.option("--json", "json_mode", is_flag=True, help="Output JSON only.")
def update(
    project: str,
    compact: bool,
    decision_title: str | None,
    decision_why: str | None,
    decision_slug: str | None,
    summary_file: str | None,
    dry_run: bool,
    json_mode: bool,
) -> None:
    """Sync project changes into the knowledge tree."""
    args = ["--project", project]
    if compact:
        args.append("--compact")
    if decision_title:
        args.extend(["--decision-title", decision_title])
    if decision_why:
        args.extend(["--decision-why", decision_why])
    if decision_slug:
        args.extend(["--decision-slug", decision_slug])
    if summary_file:
        args.extend(["--summary-file", summary_file])
    _add_common_flags(args, dry_run=dry_run, json_mode=json_mode)
    sys.exit(run_bash_script("update-knowledge.sh", args))


# -- doctor ---------------------------------------------------------------- #


@main.command()
@click.option("--project", default=".", type=click.Path(exists=True), help="Project repo root.")
@click.option("--dry-run", is_flag=True, help="Preview changes without writing.")
@click.option("--json", "json_mode", is_flag=True, help="Output JSON only.")
def doctor(project: str, dry_run: bool, json_mode: bool) -> None:
    """Validate setup, pointer resolution, and note structure."""
    args = ["--project", project]
    _add_common_flags(args, dry_run=dry_run, json_mode=json_mode)
    sys.exit(run_bash_script("doctor.sh", args))


# -- validate -------------------------------------------------------------- #


@main.command()
@click.option("--project", default=".", type=click.Path(exists=True), help="Project repo root.")
@click.option("--dry-run", is_flag=True, help="Preview changes without writing.")
@click.option("--json", "json_mode", is_flag=True, help="Output JSON only.")
def validate(project: str, dry_run: bool, json_mode: bool) -> None:
    """Validate the knowledge layout and operational links."""
    args = ["--project", project]
    _add_common_flags(args, dry_run=dry_run, json_mode=json_mode)
    sys.exit(run_bash_script("validate-knowledge.sh", args))


# -- ship ------------------------------------------------------------------ #


@main.command()
@click.option("--project", default=".", type=click.Path(exists=True), help="Project repo root.")
@click.option("--message", default=None, help="Custom commit message.")
@click.option("--open-pr", is_flag=True, help="Create a pull request after pushing.")
@click.option("--dry-run", is_flag=True, help="Preview changes without writing.")
@click.option("--json", "json_mode", is_flag=True, help="Output JSON only.")
def ship(
    project: str,
    message: str | None,
    open_pr: bool,
    dry_run: bool,
    json_mode: bool,
) -> None:
    """Validate, sync, commit, push, and optionally create a PR."""
    args = ["--project", project]
    if message:
        args.extend(["--message", message])
    if open_pr:
        args.append("--open-pr")
    _add_common_flags(args, dry_run=dry_run, json_mode=json_mode)
    sys.exit(run_bash_script("ship.sh", args))


# -- global-sync ----------------------------------------------------------- #


@main.command("global-sync")
@click.option("--project", default=".", type=click.Path(exists=True), help="Project repo root.")
@click.option("--dry-run", is_flag=True, help="Preview changes without writing.")
@click.option("--json", "json_mode", is_flag=True, help="Output JSON only.")
def global_sync(project: str, dry_run: bool, json_mode: bool) -> None:
    """Import safe local tooling config into the knowledge tree."""
    args = ["--project", project]
    _add_common_flags(args, dry_run=dry_run, json_mode=json_mode)
    sys.exit(run_bash_script("global-knowledge-sync.sh", args))


# -- graphify-sync --------------------------------------------------------- #


@main.command("graphify-sync")
@click.option("--project", default=".", type=click.Path(exists=True), help="Project repo root.")
@click.option("--source", default=None, help="Override source path for graph artifacts.")
@click.option("--dry-run", is_flag=True, help="Preview changes without writing.")
@click.option("--json", "json_mode", is_flag=True, help="Output JSON only.")
def graphify_sync(
    project: str,
    source: str | None,
    dry_run: bool,
    json_mode: bool,
) -> None:
    """Import optional graph/discovery artifacts into Evidence and Outputs."""
    args = ["--project", project]
    if source:
        args.extend(["--source", source])
    _add_common_flags(args, dry_run=dry_run, json_mode=json_mode)
    sys.exit(run_bash_script("graphify-sync.sh", args))


# -- compact --------------------------------------------------------------- #


@main.command()
@click.option("--project", default=".", type=click.Path(exists=True), help="Project repo root.")
@click.option("--dry-run", is_flag=True, help="Preview changes without writing.")
@click.option("--json", "json_mode", is_flag=True, help="Output JSON only.")
def compact(project: str, dry_run: bool, json_mode: bool) -> None:
    """Compact memory notes conservatively."""
    args = ["--project", project]
    _add_common_flags(args, dry_run=dry_run, json_mode=json_mode)
    sys.exit(run_bash_script("compact-memory.sh", args))


# -- measure-tokens -------------------------------------------------------- #


@main.command(
    "measure-tokens",
    context_settings={
        "ignore_unknown_options": True,
        "allow_extra_args": True,
        "allow_interspersed_args": False,
    },
)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def measure_tokens(args: tuple[str, ...]) -> None:
    """Estimate repo-controlled context token savings.

    \b
    Subcommands: compare, log-run, summarize-log.
    Pass --help after the subcommand for its options:
      agent-knowledge measure-tokens compare --help
    """
    if not args:
        sys.exit(run_python_script("measure-token-savings.py", ["--help"]))
    sys.exit(run_python_script("measure-token-savings.py", list(args)))


# -- setup ----------------------------------------------------------------- #


def _link(src: Path, dst: Path, label: str, dry_run: bool) -> None:
    if dst.is_symlink() and dst.resolve() == src.resolve():
        click.echo(f"  up to date: {label}", err=True)
        return
    if dry_run:
        click.echo(f"  [dry-run] would link: {label}", err=True)
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        dst.unlink() if dst.is_file() or dst.is_symlink() else None
    dst.symlink_to(src)
    click.echo(f"  linked: {label}", err=True)


@main.command()
@click.option("--dry-run", is_flag=True, help="Preview changes without writing.")
def setup(dry_run: bool) -> None:
    """Install global Cursor rules, skills, and Claude config into your home directory."""
    assets = get_assets_dir()
    home = Path.home()

    click.echo("agent-knowledge: setting up global config", err=True)
    if dry_run:
        click.echo("(dry-run mode)", err=True)
    click.echo("", err=True)

    # Cursor rules
    rules_dst = home / ".cursor" / "rules"
    rules_dst.mkdir(parents=True, exist_ok=True)
    click.echo("[cursor rules -> ~/.cursor/rules/]", err=True)
    for src in sorted((assets / "rules-global").glob("*.mdc")):
        _link(src, rules_dst / src.name, src.name, dry_run)
    click.echo("", err=True)

    # Skills
    skills_dst = home / ".cursor" / "skills"
    skills_dst.mkdir(parents=True, exist_ok=True)
    click.echo("[skills -> ~/.cursor/skills/]", err=True)
    for src in sorted((assets / "skills").iterdir()):
        if src.is_dir():
            _link(src, skills_dst / src.name, src.name, dry_run)
    click.echo("", err=True)

    # Cursor-specific skills
    skills_cursor_dst = home / ".cursor" / "skills-cursor"
    skills_cursor_dst.mkdir(parents=True, exist_ok=True)
    click.echo("[skills-cursor -> ~/.cursor/skills-cursor/]", err=True)
    for src in sorted((assets / "skills-cursor").iterdir()):
        if src.is_dir():
            _link(src, skills_cursor_dst / src.name, src.name, dry_run)
    click.echo("", err=True)

    # Claude Code
    claude_install = assets / "claude" / "scripts" / "install.sh"
    click.echo("[claude code -> ~/.claude/CLAUDE.md]", err=True)
    if dry_run:
        click.echo("  [dry-run] would run: claude/scripts/install.sh", err=True)
    elif claude_install.is_file():
        subprocess.run(["bash", str(claude_install)], check=False)
    click.echo("", err=True)

    click.echo("Done.", err=True)
