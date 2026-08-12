"""CLI entry point for project-bedrock (bedrock command)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import click

from agent_knowledge import __version__
from agent_knowledge.runtime.paths import get_assets_dir
from agent_knowledge.runtime.shell import open_in_browser, run_bash_script, run_python_script


def _open_in_browser(target: Path | str) -> None:
    """Open a local file or URL in the system browser, or print it if there is none."""
    target = target.as_uri() if isinstance(target, Path) else target
    if not open_in_browser(target):
        click.echo(f"no display detected; open it yourself: {target}", err=True)


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
@click.version_option(version=__version__, prog_name="bedrock")
def main() -> None:
    """Adaptive, file-based project knowledge for AI coding agents."""


# -- helpers --------------------------------------------------------------- #

def _resolve_project(project: str) -> str:
    """Resolve --project to the enclosing bedrock project, walking up if needed.

    Hooks run in whatever directory the agent happened to be in, which is not
    always the repo root. Walking up lets a generated hook command carry no path
    at all -- nothing to hardcode, nothing to quote, and nothing that depends on
    the shell expanding a variable (Windows hooks may run under PowerShell).

    A directory that is itself a connected project is returned untouched, so an
    explicit --project always wins.
    """
    start = Path(project).resolve()
    for candidate in (start, *start.parents):
        if (candidate / ".agent-project.yaml").is_file():
            return str(candidate)
    return str(start)


def _patch_gitignore_for_local_knowledge(repo_path: Path, json_mode: bool) -> None:
    """Append local-mode knowledge gitignore patterns if not already present."""
    from agent_knowledge.runtime.gitignore import ensure_patterns

    added = ensure_patterns(repo_path)
    if added and not json_mode:
        click.echo("  .gitignore: added local knowledge patterns", err=True)


# -- init ------------------------------------------------------------------ #


@main.command()
@click.option("--slug", default=None, help="Project slug (default: repo directory name).")
@click.option("--repo", default=".", type=click.Path(exists=True), help="Project repo path (default: cwd).")
@click.option("--knowledge-home", default=None, help="Knowledge root (default: $AGENT_KNOWLEDGE_HOME or ~/agent-os/projects).")
@click.option("--real-path", default=None, help="Explicit external knowledge folder path (only used with --external).")
@click.option("--external", "external_mode", is_flag=True, help="Store knowledge in ~/agent-os/projects/<slug>/ (external vault). ./bedrock becomes a symlink.")
@click.option("--local", "local_compat", is_flag=True, hidden=True, help="No-op: local is now the default. Kept for backward compatibility.")
@click.option("--no-integrations", is_flag=True, help="Skip auto-detection and installation of tool integrations.")
@click.option("--dry-run", is_flag=True, help="Preview changes without writing.")
@click.option("--json", "json_mode", is_flag=True, help="Output JSON only.")
@click.option("--force", is_flag=True, help="Overwrite existing files.")
def init(
    slug: str | None,
    repo: str,
    knowledge_home: str | None,
    real_path: str | None,
    external_mode: bool,
    local_compat: bool,
    no_integrations: bool,
    dry_run: bool,
    json_mode: bool,
    force: bool,
) -> None:
    """Initialize a project: create knowledge folder, pointer, and metadata.

    When run with no arguments inside a repo, infers slug from the directory
    name, auto-detects tool integrations, and installs everything needed.

    \b
    Storage modes:
      default   Knowledge lives in ./bedrock/ inside the repo
                (git-tracked). ~/agent-os/projects/<slug>/ is a symlink
                back to the repo folder. Noisy subfolders are added to
                .gitignore automatically.
      --external  Knowledge lives in ~/agent-os/projects/<slug>/ (external
                vault). ./bedrock is a symlink to that folder.
    """
    from agent_knowledge.runtime.integrations import detect, install_all

    repo_path = Path(repo).resolve()
    if slug is None:
        slug = _sanitize_slug(repo_path.name)

    if knowledge_home is None:
        knowledge_home = os.environ.get("AGENT_KNOWLEDGE_HOME")

    # Core setup: knowledge folder, .agent-project.yaml, AGENTS.md, bootstrap
    args = ["--slug", slug, "--repo", str(repo_path)]
    if knowledge_home:
        args.extend(["--knowledge-home", knowledge_home])
    if real_path:
        args.extend(["--real-path", real_path])
    if external_mode:
        args.append("--external")
    args.append("--install-hooks")
    _add_common_flags(args, dry_run=dry_run, json_mode=json_mode, force=force)
    rc = run_bash_script("install-project-links.sh", args)
    if rc != 0:
        sys.exit(rc)

    # Patch .gitignore to exclude noisy knowledge subfolders (local mode = default)
    if not external_mode and not dry_run:
        _patch_gitignore_for_local_knowledge(repo_path, json_mode)

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

    # Auto-import repo history into Evidence/
    if not dry_run:
        import_args = ["--project", str(repo_path)]
        if json_mode:
            import_args.append("--json")
        rc_import = run_bash_script("import-agent-history.sh", import_args)
        if not json_mode and rc_import == 0:
            click.echo("  Import: repo history indexed into Evidence/", err=True)

    # Lightweight history backfill — runs automatically for existing repos
    if not dry_run:
        from agent_knowledge.runtime.history import run_backfill

        vault_dir = repo_path / "bedrock"
        if vault_dir.is_dir():
            result = run_backfill(
                repo_path,
                vault_dir,
                project_slug=slug,
                dry_run=False,
            )
            if not json_mode and result["action"] == "backfilled":
                click.echo(
                    f"  History: backfilled {result['events_written']} events "
                    f"({result['git_commits']} commits, {result['git_tags']} tags)",
                    err=True,
                )

    if not json_mode:
        prompt = "Read AGENTS.md and ./bedrock/STATUS.md, then onboard this project."
        header = "Paste in your agent chat:"
        width = max(len(prompt), len(header)) + 2
        border = "+" + "-" * width + "+"
        click.echo("", err=True)
        click.secho(border, fg="cyan", err=True)
        click.secho(f"| {header:<{width - 2}} |", fg="cyan", err=True)
        click.secho(border, fg="cyan", err=True)
        click.secho(f"  {prompt}", bold=True, err=True)
        click.secho(border, fg="cyan", err=True)
        click.echo("", err=True)

        _maybe_star()


_REPO_URL = "https://github.com/robotaitai/project-bedrock"
_STAR_MARKER = Path.home() / ".bedrock-starred"


def _maybe_star() -> None:
    """Prompt to star the repo once, then never again. Skips in non-interactive shells."""
    if _STAR_MARKER.exists():
        return
    if not sys.stderr.isatty():
        return
    try:
        click.echo("", err=True)
        if click.confirm(
            click.style("Like bedrock? Star it on GitHub", fg="yellow"),
            default=True,
            err=True,
        ):
            _open_in_browser(_REPO_URL)
    except (EOFError, KeyboardInterrupt):
        click.echo("", err=True)
    _STAR_MARKER.touch()


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
      1. Copy agent_docs/memory/*.md -> bedrock/Memory/ (newer only)
      2. Extract recent git log into Evidence/raw/git-recent.md
      4. Update last_project_sync in STATUS.md
    """
    import json as json_mod

    from agent_knowledge.runtime.sync import run_sync

    repo_path = Path(_resolve_project(project))
    result = run_sync(repo_path, dry_run=dry_run)

    if json_mode:
        # Step keys stay at the top level of "sync" for backward compatibility.
        payload = dict(result["steps"])
        payload["action"] = result["action"]
        payload["warnings"] = result["warnings"]
        click.echo(json_mod.dumps({"sync": payload}, indent=2))
    else:
        for step, actions in result["steps"].items():
            click.echo(f"[{step}]", err=True)
            for action in actions:
                click.echo(action, err=True)
            click.echo("", err=True)

        for warning in result["warnings"]:
            click.secho(warning, fg="yellow", err=True)

        if result["action"] == "blocked":
            # Exits 0: this runs from SessionStart joined by &&, so failing here
            # would take down the whole agent session.
            return
        if dry_run:
            click.echo("(dry-run -- no changes written)", err=True)
        else:
            click.secho("Sync complete.", bold=True, err=True)


# -- bootstrap ------------------------------------------------------------- #


@main.command()
@click.option("--project", default=".", type=click.Path(exists=True), help="Project repo root.")
@click.option("--profile", default=None, help="Profile hint (web-app, robotics, ml-platform, hybrid). Advisory only.")
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
    project = _resolve_project(project)
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
        # Relative to the project, not to wherever the agent happened to be.
        args.extend(["--summary-file", str(Path(project) / summary_file)])
    _add_common_flags(args, dry_run=dry_run, json_mode=json_mode)
    sys.exit(run_bash_script("update-knowledge.sh", args))


# -- doctor ---------------------------------------------------------------- #


@main.command()
@click.option("--project", default=".", type=click.Path(exists=True), help="Project repo root.")
@click.option("--dry-run", is_flag=True, help="Preview changes without writing.")
@click.option("--json", "json_mode", is_flag=True, help="Output JSON only.")
def doctor(project: str, dry_run: bool, json_mode: bool) -> None:
    """Validate setup, pointer resolution, and note structure.

    Reports whether the project integration is stale and suggests
    `bedrock refresh-system` when the framework version has changed.
    """
    from agent_knowledge.runtime.refresh import (
        is_stale, check_cursor_integration, check_claude_integration,
        check_stale_notes,
    )
    from agent_knowledge.runtime.history import history_exists
    from agent_knowledge.runtime.health import check_install_health

    repo_root = Path(_resolve_project(project))

    # Install health check (legacy/shadowed package copies that block updates)
    install_issues = check_install_health()
    if install_issues and not json_mode:
        for issue in install_issues:
            click.secho(f"Warning: {issue}", fg="yellow", err=True)
        click.echo("", err=True)

    # Framework version staleness check
    stale, prior, current = is_stale(repo_root)
    if stale and not json_mode:
        if prior:
            click.secho(
                f"Warning: project integration is at v{prior}, installed framework is v{current}. "
                f"Run: bedrock refresh-system",
                fg="yellow",
                err=True,
            )
        else:
            click.secho(
                f"Warning: no framework_version in STATUS.md. "
                f"Run: bedrock refresh-system",
                fg="yellow",
                err=True,
            )
        click.echo("", err=True)

    # Layout-version check -- which side of the version gap this install is on
    if not json_mode:
        from agent_knowledge.runtime.migrations import LAYOUT_VERSION, read_layout_version

        project_layout = read_layout_version(repo_root)
        if project_layout > LAYOUT_VERSION:
            click.secho(
                f"Warning: project layout {project_layout} is newer than this install "
                f"({LAYOUT_VERSION}). Run: pip install -U project-bedrock",
                fg="yellow",
                err=True,
            )
            click.echo("", err=True)
        elif project_layout < LAYOUT_VERSION:
            click.secho(
                f"Warning: project layout {project_layout} is behind this install "
                f"({LAYOUT_VERSION}). Run: bedrock refresh-system",
                fg="yellow",
                err=True,
            )
            click.echo("", err=True)

    # Cursor integration health check
    cursor_health = check_cursor_integration(repo_root)
    if not cursor_health["healthy"] and not json_mode:
        for issue in cursor_health["issues"]:
            click.secho(f"Warning: {issue}", fg="yellow", err=True)
        click.echo("", err=True)

    # Claude integration health check
    claude_health = check_claude_integration(repo_root)
    if not claude_health["healthy"] and not json_mode:
        for issue in claude_health["issues"]:
            click.secho(f"Warning: {issue}", fg="yellow", err=True)
        click.echo("", err=True)

    # History existence check
    vault_dir = repo_root / "bedrock"
    if vault_dir.is_dir() and not history_exists(vault_dir) and not json_mode:
        click.secho(
            "Note: no History/ layer found. Run: bedrock backfill-history",
            fg="cyan",
            err=True,
        )
        click.echo("", err=True)

    # Durable-branch note staleness check
    stale_notes = check_stale_notes(repo_root)
    if stale_notes and not json_mode:
        click.secho(
            f"Warning: {len(stale_notes)} Memory note(s) may be stale "
            f"(source changed after note was last updated):",
            fg="yellow",
            err=True,
        )
        for w in stale_notes:
            click.secho(
                f"  {w['path']}  [updated {w['note_updated']}, src last changed {w['last_src_commit']}]",
                fg="yellow",
                err=True,
            )
            if w.get("update_when"):
                click.secho(f"    update when: {w['update_when'][:120]}", fg="yellow", err=True)
        click.secho(
            "  Review these notes and update with: bedrock sync",
            fg="yellow",
            err=True,
        )
        click.echo("", err=True)

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


@main.command("global-sync", hidden=True)
@click.option("--project", default=".", type=click.Path(exists=True), help="Project repo root.")
@click.option("--dry-run", is_flag=True, help="Preview changes without writing.")
@click.option("--json", "json_mode", is_flag=True, help="Output JSON only.")
def global_sync(project: str, dry_run: bool, json_mode: bool) -> None:
    """Import safe local tooling config into the knowledge tree."""
    args = ["--project", project]
    _add_common_flags(args, dry_run=dry_run, json_mode=json_mode)
    sys.exit(run_bash_script("global-knowledge-sync.sh", args))


# -- graphify-sync --------------------------------------------------------- #


@main.command("graphify-sync", hidden=True)
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
    hidden=True,
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
      bedrock measure-tokens compare --help
    """
    if not args:
        sys.exit(run_python_script("measure-token-savings.py", ["--help"]))
    sys.exit(run_python_script("measure-token-savings.py", list(args)))


# -- search ---------------------------------------------------------------- #


@main.command()
@click.argument("query", required=False, default="")
@click.option("--project", default=".", type=click.Path(exists=True), help="Project repo root.")
@click.option("--limit", default=10, show_default=True, help="Max results.")
@click.option("--all", "include_all", is_flag=True, help="Include Evidence/Outputs in results (default: Memory-first).")
@click.option("--json", "json_mode", is_flag=True, help="Output JSON only.")
def search(query: str, project: str, limit: int, include_all: bool, json_mode: bool) -> None:
    """Search the knowledge index. Prefers Memory/ over Evidence/Outputs.

    \b
    Layer 1: loads the compact index (Views/graph/knowledge-index.json).
    Layer 2: returns a ranked shortlist of relevant notes.
    Layer 3: use --full or read the note files directly for full content.
    """
    import json as json_mod

    from agent_knowledge.runtime.index import search as idx_search

    vault = Path(project).resolve() / "bedrock"
    if not vault.is_dir():
        click.echo("No bedrock vault found. Run: bedrock init", err=True)
        sys.exit(1)

    if not query:
        click.echo("Usage: bedrock search <query>", err=True)
        sys.exit(0)

    results = idx_search(vault, query, max_results=limit, include_non_canonical=include_all)

    if json_mode:
        click.echo(json_mod.dumps({"query": query, "results": results}, indent=2))
        return

    if not results:
        click.echo(f"No results for: {query}", err=True)
        return

    click.secho(f"Results for '{query}' ({len(results)} found):", bold=True, err=True)
    for r in results:
        canonical_tag = "[Memory]" if r["canonical"] else f"[{r['folder']}]"
        entry_tag = " (branch entry)" if r["is_branch_entry"] else ""
        click.echo(f"\n  {canonical_tag}{entry_tag} {r['path']}", err=True)
        click.echo(f"    {r['title']}", err=True)
        if r.get("summary"):
            click.echo(f"    {r['summary'][:120]}", err=True)


# -- index ----------------------------------------------------------------- #


@main.command("index")
@click.option("--project", default=".", type=click.Path(exists=True), help="Project repo root.")
@click.option("--dry-run", is_flag=True, help="Preview changes without writing.")
@click.option("--json", "json_mode", is_flag=True, help="Output JSON only.")
def index_cmd(project: str, dry_run: bool, json_mode: bool) -> None:
    """Regenerate the compact knowledge index.

    Produces Views/graph/knowledge-index.json (machine-readable) and
    Views/graph/knowledge-index.md (compact human/agent catalog) by default,
    with legacy Outputs/ fallback for older projects. The index is generated
    output -- not curated memory.
    """
    import json as json_mod

    from agent_knowledge.runtime.index import write_index

    vault = Path(project).resolve() / "bedrock"
    if not vault.is_dir():
        click.echo("No bedrock vault found. Run: bedrock init", err=True)
        sys.exit(1)

    actions = write_index(vault, dry_run=dry_run)

    if json_mode:
        click.echo(json_mod.dumps({"index": actions}, indent=2))
    else:
        for action in actions:
            click.echo(action, err=True)


# -- export-html ----------------------------------------------------------- #


@main.command("export-html")
@click.option("--project", default=".", type=click.Path(exists=True), help="Project repo root.")
@click.option("--output-dir", default=None, type=click.Path(), help="Output directory (default: Views/site/, with legacy Outputs/site/ fallback).")
@click.option("--include-evidence", is_flag=True, default=True, show_default=True, help="Include Evidence/ notes in the site.")
@click.option("--no-evidence", "include_evidence", flag_value=False, help="Exclude Evidence/ notes from the site.")
@click.option("--dry-run", is_flag=True, help="Preview what would be generated without writing.")
@click.option("--json", "json_mode", is_flag=True, help="Output JSON summary only.")
@click.option("--open", "open_browser", is_flag=True, help="Open the generated site in the browser after export.")
def export_html(
    project: str,
    output_dir: str | None,
    include_evidence: bool,
    dry_run: bool,
    json_mode: bool,
    open_browser: bool,
) -> None:
    """Build a polished static HTML site from the knowledge vault.

    Generates Views/site/index.html and Views/site/data/knowledge.json by
    default, with legacy Outputs/site/ fallback for older projects. Opens in
    any browser without Obsidian. Memory/ is primary; Evidence/ and generated
    views are clearly marked non-canonical.

    \b
    Examples:
      bedrock export-html
      bedrock export-html --open
      bedrock export-html --dry-run
      bedrock export-html --no-evidence
    """
    import json as json_mod

    from agent_knowledge.runtime.site import generate_site

    vault = Path(project).resolve() / "bedrock"
    if not vault.is_dir():
        click.echo("No bedrock vault found. Run: bedrock init", err=True)
        sys.exit(1)

    out_dir = Path(output_dir).resolve() if output_dir else None
    result = generate_site(
        vault,
        out_dir,
        dry_run=dry_run,
        include_evidence=include_evidence,
    )

    if json_mode:
        click.echo(json_mod.dumps(result, indent=2))
        return

    if dry_run:
        click.echo(f"[dry-run] would generate site: {result['site_dir']}", err=True)
        click.echo(f"  {result['branch_count']} branches, {result['decision_count']} decisions, {result['evidence_count']} evidence items", err=True)
    else:
        action = result["action"]
        click.echo(f"{action}: {result['site_dir']}", err=True)
        click.echo(f"  index.html — {result['branch_count']} branches, {result['decision_count']} decisions, {result['note_count']} notes total", err=True)
        click.echo(f"  data/knowledge.json — structured site data", err=True)
        if open_browser:
            _open_in_browser(Path(result["index_html"]))


# -- view ------------------------------------------------------------------ #


@main.command()
@click.option("--project", default=".", type=click.Path(exists=True), help="Project repo root.")
@click.option("--output-dir", default=None, type=click.Path(), help="Override output directory for the site.")
@click.option("--serve", is_flag=True, help="Serve the site over a local HTTP server instead of file:// (blocks until Ctrl-C).")
@click.option("--port", default=0, type=click.IntRange(0, 65535), help="Port for --serve (default: any free port).")
@click.option("--no-open", "no_open", is_flag=True, help="Generate the site and print its path without opening a browser.")
def view(project: str, output_dir: str | None, serve: bool, port: int, no_open: bool) -> None:
    """Build the knowledge site and open it in the browser.

    Equivalent to export-html --open. No Obsidian required.
    The site is generated into Views/site/ by default and opened via file://.
    Use --serve when the browser restricts local files (strict CSP, sandboxed
    profiles) or when working over SSH, where the port can be forwarded.
    On a headless box or an SSH session the browser is skipped and the path is
    printed instead; --no-open forces that everywhere.
    """
    from agent_knowledge.runtime.site import generate_site

    vault = Path(project).resolve() / "bedrock"
    if not vault.is_dir():
        click.echo("No bedrock vault found. Run: bedrock init", err=True)
        sys.exit(1)

    out_dir = Path(output_dir).resolve() if output_dir else None
    result = generate_site(vault, out_dir)
    click.echo(f"{result['action']}: {result['site_dir']}", err=True)

    if serve:
        _serve_site(Path(result["site_dir"]), Path(result["index_html"]), port, no_open=no_open)
        return

    if no_open:
        click.echo(Path(result["index_html"]).as_uri(), err=True)
        return

    _open_in_browser(Path(result["index_html"]))


def _serve_site(site_dir: Path, index_html: Path, port: int, *, no_open: bool = False) -> None:
    """Serve a generated site over a local HTTP server until interrupted."""
    import functools
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(site_dir))
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    except OSError as exc:
        click.echo(f"Could not start local server on port {port}: {exc}", err=True)
        sys.exit(1)

    try:
        rel = index_html.relative_to(site_dir).as_posix()
    except ValueError:
        rel = "index.html"
    url = f"http://127.0.0.1:{httpd.server_address[1]}/{rel}"
    click.echo(f"serving: {url}  (Ctrl-C to stop)", err=True)
    if not no_open:
        open_in_browser(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        click.echo("", err=True)
    finally:
        httpd.server_close()


# -- clean-import ---------------------------------------------------------- #


@main.command("clean-import")
@click.argument("source")
@click.option("--project", default=".", type=click.Path(exists=True), help="Project repo root.")
@click.option("--slug", default=None, help="Override output filename slug.")
@click.option("--output-dir", default=None, type=click.Path(), help="Override output directory (default: Evidence/imports/).")
@click.option("--dry-run", is_flag=True, help="Preview without writing.")
@click.option("--json", "json_mode", is_flag=True, help="Output JSON only.")
def clean_import(
    source: str,
    project: str,
    slug: str | None,
    output_dir: str | None,
    dry_run: bool,
    json_mode: bool,
) -> None:
    """Import a URL or HTML file as cleaned evidence into Evidence/imports/.

    Strips navigation, ads, scripts, and boilerplate. Writes clean markdown
    with YAML frontmatter marking it as non-canonical evidence.

    \b
    Examples:
      bedrock clean-import https://docs.example.com/api
      bedrock clean-import page.html --slug api-ref-2025-01-15
      bedrock clean-import https://... --dry-run
    """
    import json as json_mod

    from agent_knowledge.runtime.importer import clean_import as do_import

    vault = Path(project).resolve() / "bedrock"
    if output_dir:
        out_dir = Path(output_dir).resolve()
    else:
        out_dir = vault / "Evidence" / "imports"

    try:
        path, action, title = do_import(source, out_dir, slug=slug, dry_run=dry_run)
    except FileNotFoundError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    if json_mode:
        click.echo(
            json_mod.dumps(
                {
                    "action": action,
                    "path": str(path),
                    "title": title,
                    "source": source,
                    "dry_run": dry_run,
                },
                indent=2,
            )
        )
    else:
        if dry_run:
            click.echo(f"[dry-run] would create: {path}", err=True)
        elif action == "exists":
            click.echo(f"exists (same content): {path}", err=True)
        else:
            click.echo(f"{action}: {path}", err=True)
        if title and not json_mode:
            click.echo(f"  title: {title}", err=True)


# -- export-canvas --------------------------------------------------------- #


@main.command("export-canvas", hidden=True)
@click.option("--project", default=".", type=click.Path(exists=True), help="Project repo root.")
@click.option("--output", default=None, type=click.Path(), help="Output .canvas path (default: Outputs/knowledge-export.canvas).")
@click.option("--dry-run", is_flag=True, help="Preview without writing.")
def export_canvas(project: str, output: str | None, dry_run: bool) -> None:
    """Export the knowledge vault as an Obsidian Canvas (.canvas) file.

    Generates a spatial graph of Memory/ notes with edges derived from
    markdown links. Open in Obsidian with Core plugins > Canvas enabled.

    This is an optional Output: non-canonical and regeneratable.
    The system works fully without it.
    """
    from agent_knowledge.runtime.canvas import export_canvas as do_export

    vault = Path(project).resolve() / "bedrock"
    if not vault.is_dir():
        click.echo("No bedrock vault found. Run: bedrock init", err=True)
        sys.exit(1)

    out_path = Path(output).resolve() if output else None
    path, action = do_export(vault, out_path, dry_run=dry_run)

    if dry_run:
        click.echo(f"[dry-run] would write: {path}", err=True)
    else:
        click.echo(f"{action}: {path}", err=True)
        click.echo("  Open in Obsidian: Core plugins > Canvas", err=True)


# -- backfill-history ------------------------------------------------------ #


@main.command("backfill-history", hidden=True)
@click.option("--project", default=".", type=click.Path(exists=True), help="Project repo root.")
@click.option("--dry-run", is_flag=True, help="Preview what would be written without writing.")
@click.option("--json", "json_mode", is_flag=True, help="Output JSON summary only.")
@click.option("--force", is_flag=True, hidden=True, help="Re-run even if up to date.")
def backfill_history(project: str, dry_run: bool, json_mode: bool, force: bool) -> None:
    """Backfill lightweight project history from git and integration artifacts.

    Creates History/events.ndjson, History/history.md, and a compact timeline
    note. Runs automatically during `bedrock init` on existing repos.

    History records what happened over time (milestones, releases, integrations)
    without replacing Memory/ or duplicating git. Safe to run multiple times.

    \b
    Examples:
      bedrock backfill-history
      bedrock backfill-history --dry-run
      bedrock backfill-history --json
    """
    import json as json_mod

    from agent_knowledge.runtime.history import run_backfill

    repo_root = Path(project).resolve()
    vault_dir = repo_root / "bedrock"

    if not vault_dir.is_dir():
        msg = {"error": "No bedrock vault found. Run: bedrock init"}
        if json_mode:
            click.echo(json_mod.dumps(msg))
        else:
            click.secho(msg["error"], fg="red", err=True)
        raise SystemExit(1)

    slug = repo_root.name
    yaml_path = repo_root / ".agent-project.yaml"
    if yaml_path.is_file():
        for line in yaml_path.read_text(encoding="utf-8", errors="replace").splitlines():
            m = __import__("re").match(r"^slug:\s*(.+)$", line.strip())
            if m:
                slug = m.group(1).strip().strip("\"'")
                break

    result = run_backfill(repo_root, vault_dir, project_slug=slug, dry_run=dry_run, force=force)

    if json_mode:
        click.echo(json_mod.dumps(result, indent=2))
        return

    action = result["action"]
    if action == "up-to-date":
        click.secho(f"History is up to date. (slug: {slug})", bold=True, err=True)
    elif action == "dry-run":
        click.echo(f"[dry-run] would backfill for: {slug}", err=True)
    else:
        click.secho(
            f"Backfilled: {result['events_written']} new events, "
            f"{result['events_skipped']} skipped.",
            bold=True,
            err=True,
        )

    click.echo("", err=True)

    if result["git_commits"]:
        click.echo(
            f"  git: {result['git_commits']} total commits, "
            f"{result['git_tags']} tags, "
            f"started {result['git_first_commit'] or 'unknown'}",
            err=True,
        )
    if result["integrations"]:
        click.echo(f"  integrations: {', '.join(result['integrations'])}", err=True)
    if result["changes"] and not dry_run:
        for c in result["changes"]:
            click.echo(f"  wrote: {c}", err=True)

    click.echo("", err=True)


# -- absorb ---------------------------------------------------------------- #


@main.command("absorb")
@click.option("--project", default=".", type=click.Path(exists=True), help="Project repo root.")
@click.option("--dry-run", is_flag=True, help="Preview what would be imported without writing.")
@click.option("--json", "json_mode", is_flag=True, help="Output JSON summary only.")
@click.option("--no-decisions", is_flag=True, help="Skip parsing ADR/decision files into decisions.md.")
def absorb(project: str, dry_run: bool, json_mode: bool, no_decisions: bool) -> None:
    """Absorb existing project docs and knowledge artifacts into the vault.

    Scans the project for documentation, architecture notes, ADRs, changelogs,
    and similar knowledge-bearing files. Copies them into Evidence/imports/ as
    non-canonical evidence, parses any decision/ADR records into decisions.md,
    and generates Outputs/absorb-manifest.md for agent review.

    The agent should then read the manifest and promote relevant content to
    Memory/ branches. This command does the mechanical ingestion; curation
    remains the agent's responsibility.

    \b
    Sources discovered:
      - Root-level docs: ARCHITECTURE.md, CHANGELOG.md, DESIGN.md, etc.
      - docs/, documentation/, wiki/ directories
      - adr/, decisions/, docs/adr/ directories (also parsed as ADRs)
      - Respects .agentknowledgeignore

    \b
    Outputs:
      - Evidence/imports/<file>.md  -- non-canonical copies with metadata
      - Memory/decisions.md  -- parsed ADR entries appended
      - Outputs/absorb-manifest.md  -- manifest listing all imports
      - History/events.ndjson  -- absorb event recorded
    """
    from agent_knowledge.runtime.absorb import run_absorb

    repo_path = Path(project).resolve()
    vault_dir = repo_path / "bedrock"

    if not vault_dir.exists():
        if json_mode:
            click.echo(
                __import__("json").dumps({"error": "bedrock vault not found; run: bedrock init"}),
                err=False,
            )
        else:
            click.secho("Error: bedrock vault not found. Run: bedrock init", fg="red", err=True)
        raise SystemExit(1)

    if not json_mode:
        click.echo(f"Absorbing project knowledge: {repo_path}", err=True)
        if dry_run:
            click.echo("(dry-run -- no files will be written)", err=True)

    result = run_absorb(
        repo_path,
        vault_dir,
        project_slug=repo_path.name,
        dry_run=dry_run,
        include_decisions=not no_decisions,
    )

    if json_mode:
        import json as _json
        summary = {k: v for k, v in result.items() if k != "results"}
        click.echo(_json.dumps(summary))
        return

    imported = result["imported"]
    already = result["already_present"]
    decisions = result["decisions_parsed"]
    found = result["sources_found"]
    manifest = result["manifest"]

    if found == 0:
        click.echo("  No knowledge sources found in project.", err=True)
        click.echo("  Looked for: docs/, adr/, decisions/, ARCHITECTURE.md, CHANGELOG.md, etc.", err=True)
        return

    click.echo(f"  Found:     {found} source files", err=True)
    click.echo(f"  Imported:  {imported} new files -> Evidence/imports/", err=True)
    if already:
        click.echo(f"  Skipped:   {already} already present", err=True)
    if decisions:
        click.echo(f"  Decisions: {decisions} ADR entries parsed -> Memory/decisions.md", err=True)
    if not dry_run:
        click.echo(f"  Manifest:  {manifest}", err=True)
        click.echo("", err=True)
        click.echo(
            "Next: ask your agent to read Outputs/absorb-manifest.md and update Memory/ branches.",
            err=True,
        )


# -- refresh-system -------------------------------------------------------- #


@main.command("refresh-system")
@click.option("--project", default=".", type=click.Path(exists=True), help="Project repo root.")
@click.option("--dry-run", is_flag=True, help="Preview what would change without writing.")
@click.option("--json", "json_mode", is_flag=True, help="Output JSON summary only.")
@click.option("--force", is_flag=True, hidden=True, help="Force updates even when up-to-date.")
def refresh_system(project: str, dry_run: bool, json_mode: bool, force: bool) -> None:
    """Refresh project integration files to the current framework version.

    Updates bridge files (AGENTS.md header, Cursor hooks, CLAUDE.md, Codex config)
    and metadata version markers (STATUS.md, .agent-project.yaml).

    Memory/, Evidence/, and project-curated content are never touched.
    Safe to run after `pip install -U project-bedrock`.

    \b
    Examples:
      bedrock refresh-system
      bedrock refresh-system --dry-run
      bedrock refresh-system --json
    """
    import json as json_mod

    from agent_knowledge.runtime.refresh import run_refresh

    repo_root = Path(_resolve_project(project))
    result = run_refresh(repo_root, dry_run=dry_run, force=force)

    if json_mode:
        click.echo(json_mod.dumps(result, indent=2))
        return

    if result["action"] == "blocked":
        for w in result.get("warnings", []):
            click.secho(f"Warning: {w}", fg="yellow", err=True)
        click.echo("", err=True)
        click.echo("No files were changed.", err=True)
        # Deliberately exit 0: this runs from the SessionStart hook, joined by
        # &&, and a non-zero exit would degrade every session in the repo.
        return

    action = result["action"]
    version = result["framework_version"]
    prior = result.get("prior_version")
    changes = result.get("changes", [])
    warnings = result.get("warnings", [])

    if not dry_run:
        if action == "up-to-date":
            click.secho(f"Up to date. (framework v{version})", bold=True, err=True)
        elif action == "degraded":
            # Something below failed, so do not headline this as a clean refresh.
            click.secho(
                f"Refresh incomplete (framework v{version}) -- see errors below.",
                bold=True,
                fg="yellow",
                err=True,
            )
        else:
            label = "dry-run preview" if dry_run else f"Refreshed to v{version}"
            if prior and prior != version:
                label += f" (was: {prior})"
            click.secho(label, bold=True, err=True)
    else:
        click.echo(f"[dry-run] framework v{version}", err=True)

    click.echo("", err=True)

    # Group changes by action
    for c in changes:
        act = c["action"]
        target = c["target"]
        detail = c.get("detail", "")
        if act == "up-to-date":
            click.echo(f"  ok       {target}  ({detail})", err=True)
        elif act in ("updated", "created"):
            click.secho(f"  updated  {target}  ({detail})", fg="green", err=True)
        elif act == "dry-run":
            click.echo(f"  [would]  {target}  ({detail})", err=True)
        elif act == "skip":
            click.echo(f"  skip     {target}  ({detail})", err=True)
        elif act == "warn":
            click.secho(f"  warn     {target}  ({detail})", fg="yellow", err=True)
        elif act == "failed":
            click.secho(f"  failed   {target}  ({detail})", fg="red", err=True)

    if warnings:
        click.echo("", err=True)
        for w in warnings:
            click.secho(f"Warning: {w}", fg="yellow", err=True)

    click.echo("", err=True)
    if not dry_run and action not in ("up-to-date",):
        click.echo("Next: bedrock doctor --project .", err=True)


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


@main.command(name="migrate-to-local", hidden=True)
@click.option("--project", default=".", type=click.Path(exists=True), help="Project repo root (default: cwd).")
@click.option("--knowledge-home", default=None, help="bedrock home for reversed symlink (default: ~/agent-os/projects).")
@click.option("--dry-run", is_flag=True, help="Preview changes without writing.")
def migrate_to_local(project: str, knowledge_home: str | None, dry_run: bool) -> None:
    """Convert an existing external-vault project to local (in-repo) knowledge storage.

    \b
    What this does:
      1. Reads the current external vault path from ./bedrock (symlink).
      2. Copies all vault content into ./bedrock/ (real directory).
      3. Removes the old symlink and replaces it with the real directory.
      4. Creates ~/agent-os/projects/<slug>/ as a symlink back to ./bedrock/.
      5. Updates .agent-project.yaml to set vault_mode: local.
      6. Patches .gitignore with noisy-subfolder exclusions.
    """
    import re as _re
    import shutil

    repo_path = Path(project).resolve()
    pointer = repo_path / "bedrock"

    if not pointer.exists() and not pointer.is_symlink():
        click.echo("Error: ./bedrock does not exist in this project.", err=True)
        sys.exit(1)

    if pointer.exists() and not pointer.is_symlink():
        click.echo("Already in local mode (./bedrock is a real directory).", err=True)
        sys.exit(0)

    external_vault = pointer.resolve()
    click.echo(f"Current vault: {external_vault}", err=True)
    click.echo(f"Target:        {pointer} (real directory)", err=True)

    if dry_run:
        click.echo("(dry-run) would copy vault content and swap pointer", err=True)
        return

    # Copy external vault content to a temp location, then swap
    tmp = repo_path / ".bedrock-migrating"
    if tmp.exists():
        shutil.rmtree(tmp)

    click.echo("Copying vault content...", err=True)
    shutil.copytree(str(external_vault), str(tmp), symlinks=True)

    # Remove the old symlink
    pointer.unlink()

    # Move tmp to final location
    shutil.move(str(tmp), str(pointer))
    click.echo(f"  created: {pointer}/", err=True)

    # Create reversed symlink in agent-os
    kh = Path(knowledge_home) if knowledge_home else Path.home() / "agent-os" / "projects"

    # Read slug from .agent-project.yaml (simple regex, no pyyaml dep)
    project_yaml = repo_path / ".agent-project.yaml"
    slug = repo_path.name  # fallback
    if project_yaml.exists():
        try:
            m = _re.search(r"^\s*slug:\s*(\S+)", project_yaml.read_text(encoding="utf-8"), _re.MULTILINE)
            if m:
                slug = m.group(1)
        except Exception:
            pass

    agent_os_link = kh / slug
    if agent_os_link.exists() or agent_os_link.is_symlink():
        if agent_os_link.is_symlink():
            agent_os_link.unlink()
            click.echo(f"  removed old: {agent_os_link}", err=True)
        else:
            click.echo(f"  warning: {agent_os_link} is a real directory, leaving it alone", err=True)
            agent_os_link = None
    if agent_os_link:
        agent_os_link.parent.mkdir(parents=True, exist_ok=True)
        agent_os_link.symlink_to(pointer)
        click.echo(f"  linked: {agent_os_link} -> {pointer}", err=True)

    # Update .agent-project.yaml
    if project_yaml.exists():
        try:
            text = project_yaml.read_text(encoding="utf-8")
            if "vault_mode:" in text:
                text = _re.sub(r"vault_mode:\s*\S+", "vault_mode: local", text)
            else:
                text = text.replace(
                    "pointer_path:", "vault_mode: local\n  pointer_path:", 1
                )
            # Update real_path to the in-repo vault, recorded relatively so the
            # tracked file stays valid on every machine that clones the repo.
            text = _re.sub(
                r"real_path:\s*\S+",
                "real_path: ./bedrock",
                text,
            )
            project_yaml.write_text(text, encoding="utf-8")
            click.echo("  updated: .agent-project.yaml (vault_mode: local)", err=True)
        except Exception as e:
            click.echo(f"  warning: could not update .agent-project.yaml: {e}", err=True)

    # Patch .gitignore
    _patch_gitignore_for_local_knowledge(repo_path, json_mode=False)

    click.echo("", err=True)
    click.echo("Migration complete. The knowledge folder is now part of the repo.", err=True)
    click.echo("Commit bedrock/ (excluding the patterns added to .gitignore).", err=True)


@main.command(name="migrate-vault")
@click.option("--project", default=".", type=click.Path(exists=True), help="Project repo root (default: cwd).")
@click.option("--dry-run", is_flag=True, help="Preview changes without writing.")
def migrate_vault(project: str, dry_run: bool) -> None:
    """Rename ./agent-knowledge/ to ./bedrock/ for projects created before v0.4.

    \b
    What this does:
      1. Renames ./agent-knowledge/ to ./bedrock/.
      2. Updates .agent-project.yaml paths.
      3. Updates .gitignore patterns.
      4. Updates ~/agent-os/projects/<slug> symlink if present.

    Safe to run multiple times. If ./bedrock/ already exists, exits cleanly.
    """
    import re as _re
    import shutil as _shutil

    repo_path = Path(project).resolve()
    old_vault = repo_path / "agent-knowledge"
    new_vault = repo_path / "bedrock"

    if not old_vault.exists() and not old_vault.is_symlink():
        if new_vault.exists():
            click.echo("Already using ./bedrock/ -- nothing to do.", err=True)
        else:
            click.echo("Neither ./agent-knowledge/ nor ./bedrock/ found. Run: bedrock init", err=True)
        return

    if new_vault.exists():
        click.echo("./bedrock/ already exists. Remove it or merge manually before migrating.", err=True)
        sys.exit(1)

    click.echo("Migrating vault: ./agent-knowledge/ -> ./bedrock/", err=True)

    if dry_run:
        click.echo("(dry-run) would rename: agent-knowledge/ -> bedrock/", err=True)
        click.echo("(dry-run) would update: .agent-project.yaml", err=True)
        click.echo("(dry-run) would update: .gitignore", err=True)
        return

    try:
        old_vault.rename(new_vault)
    except OSError:
        _shutil.copytree(str(old_vault), str(new_vault), symlinks=True)
        _shutil.rmtree(str(old_vault))
    click.echo("  renamed: agent-knowledge/ -> bedrock/", err=True)

    # Update ~/agent-os/projects/<slug> symlink
    project_yaml = repo_path / ".agent-project.yaml"
    slug = repo_path.name
    if project_yaml.is_file():
        try:
            m = _re.search(r"^\s*slug:\s*(\S+)", project_yaml.read_text(encoding="utf-8"), _re.MULTILINE)
            if m:
                slug = m.group(1)
        except Exception:
            pass

    agent_os_link = Path.home() / "agent-os" / "projects" / slug
    if agent_os_link.is_symlink():
        try:
            if "agent-knowledge" in str(agent_os_link.resolve()):
                agent_os_link.unlink()
                agent_os_link.symlink_to(new_vault)
                click.echo(f"  updated: {agent_os_link} -> {new_vault}", err=True)
        except Exception as e:
            click.echo(f"  warning: could not update {agent_os_link}: {e}", err=True)

    # Update .agent-project.yaml
    if project_yaml.is_file():
        try:
            text = project_yaml.read_text(encoding="utf-8")
            text = text.replace("./agent-knowledge", "./bedrock")
            text = text.replace("/agent-knowledge/", "/bedrock/")
            text = text.replace("agent-knowledge update", "bedrock update")
            text = text.replace("agent-knowledge graphify-sync", "bedrock graphify-sync")
            project_yaml.write_text(text, encoding="utf-8")
            click.echo("  updated: .agent-project.yaml", err=True)
        except Exception as e:
            click.echo(f"  warning: could not update .agent-project.yaml: {e}", err=True)

    # Update .gitignore
    gitignore = repo_path / ".gitignore"
    if gitignore.is_file():
        try:
            text = gitignore.read_text(encoding="utf-8")
            if "agent-knowledge/" in text:
                text = text.replace("agent-knowledge/", "bedrock/")
                gitignore.write_text(text, encoding="utf-8")
                click.echo("  updated: .gitignore", err=True)
        except Exception as e:
            click.echo(f"  warning: could not update .gitignore: {e}", err=True)

    click.echo("", err=True)
    click.echo("Migration complete.", err=True)
    click.echo("Next steps:", err=True)
    click.echo("  1. bedrock refresh-system   (updates AGENTS.md, CLAUDE.md, Cursor rules)", err=True)
    click.echo("  2. git rm -r --cached agent-knowledge/", err=True)
    click.echo("  3. git add bedrock/ .agent-project.yaml .gitignore", err=True)
    click.echo("  4. git commit -m \"chore: migrate vault agent-knowledge -> bedrock\"", err=True)


@main.command(name="migrate-from-legacy")
@click.option("--project", default=".", type=click.Path(exists=True), help="Project repo root (default: cwd).")
@click.option("--dry-run", is_flag=True, help="Preview changes without writing.")
def migrate_from_legacy(project: str, dry_run: bool) -> None:
    """Migrate a project from agent-knowledge-cli to project-bedrock (bedrock CLI).

    \b
    What this does:
      1. Runs refresh-system to update hooks, rules, and commands to use 'bedrock'.
      2. Prints instructions to uninstall the old agent-knowledge-cli package.

    \b
    Full migration steps:
      pip uninstall agent-knowledge-cli   # remove old PyPI package
      pip install project-bedrock         # install new package (if not done yet)
      bedrock migrate-from-legacy         # update this project's integration files
    """
    from agent_knowledge.runtime.refresh import run_refresh

    repo_root = Path(project).resolve()
    vault_dir = repo_root / "bedrock"

    if not vault_dir.is_dir():
        click.secho(
            "No bedrock vault found. Run: bedrock init", fg="red", err=True
        )
        raise SystemExit(1)

    click.echo("Migrating project from agent-knowledge-cli to project-bedrock...")
    if dry_run:
        click.echo("(dry-run mode -- no files will be changed)")

    # Step 1: refresh-system updates hooks/rules/commands to use 'bedrock'
    action = run_refresh(repo_root, dry_run=dry_run, json_mode=False)

    if action == "up-to-date":
        click.secho("Integration files already up to date.", fg="green")
    else:
        click.secho("Integration files refreshed.", fg="green")

    # Step 2: print pip instructions
    click.echo("")
    click.echo("Project integration updated. Complete the migration:")
    click.echo("")
    click.echo("  pip uninstall agent-knowledge-cli   # remove old package")
    click.echo("  # The bedrock and agent-knowledge commands now both come")
    click.echo("  # from project-bedrock. The agent-knowledge alias is kept")
    click.echo("  # for backward compatibility and will be removed in a future release.")
    click.echo("")
    click.secho("Migration complete.", fg="green")


@main.command()
@click.option("--dry-run", is_flag=True, help="Preview changes without writing.")
def setup(dry_run: bool) -> None:
    """Install global Cursor rules, skills, and Claude config into your home directory."""
    assets = get_assets_dir()
    home = Path.home()

    click.echo("bedrock: setting up global config", err=True)
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


@main.command()
@click.option("--shell", type=click.Choice(["bash", "zsh", "fish"]), default=None, help="Shell type (default: auto-detect).")
@click.option("--install", is_flag=True, help="Write the eval line to your shell rc file automatically.")
def completion(shell: str | None, install: bool) -> None:
    """Enable tab completion for the bedrock CLI.

    Run once, then restart your shell (or open a new tab).
    """
    import os

    if shell is None:
        shell_bin = os.environ.get("SHELL", "")
        if "zsh" in shell_bin:
            shell = "zsh"
        elif "fish" in shell_bin:
            shell = "fish"
        else:
            shell = "bash"

    if shell == "zsh":
        eval_line = 'eval "$(_BEDROCK_COMPLETE=zsh_source bedrock)"'
        rc_file = Path.home() / ".zshrc"
    elif shell == "fish":
        eval_line = "_BEDROCK_COMPLETE=fish_source bedrock | source"
        rc_file = Path.home() / ".config" / "fish" / "config.fish"
    else:
        eval_line = 'eval "$(_BEDROCK_COMPLETE=bash_source bedrock)"'
        rc_file = Path.home() / ".bashrc"

    sentinel = "# bedrock tab completion"

    if install:
        rc_text = rc_file.read_text(encoding="utf-8") if rc_file.exists() else ""
        if eval_line in rc_text:
            click.echo(f"Already installed in {rc_file}", err=True)
        else:
            with rc_file.open("a") as f:
                f.write(f"\n{sentinel}\n{eval_line}\n")
            click.echo(f"Installed in {rc_file}. Restart your shell or run:", err=True)
            click.echo(f"  source {rc_file}", err=True)
    else:
        click.echo(f"Add this line to {rc_file}:", err=True)
        click.echo(f"  {eval_line}", err=True)
        click.echo("", err=True)
        click.echo(f"Or run: bedrock completion --install", err=True)


_GLOBAL_SENTINEL_CURSOR = "# bedrock-global"
_GLOBAL_SENTINEL_CLAUDE = "<!-- bedrock-global -->"
_GLOBAL_SENTINEL_CODEX = "<!-- bedrock-global -->"
_GLOBAL_SENTINEL_GEMINI = "<!-- bedrock-global -->"

_GLOBAL_CURSOR_RULE = """\
---
description: bedrock -- load project memory if present in any project
alwaysApply: true
---

If this project has `./bedrock/STATUS.md`:

1. Read `./bedrock/STATUS.md`
2. If `onboarding: pending` — read `AGENTS.md` and follow First-Time Onboarding
3. If `onboarding: complete` — read `./bedrock/Memory/PROJECT.md` and `./bedrock/Work/NOW.md`, then load only the relevant Memory branches

At end of session with meaningful work:
- Update stable project knowledge in `./bedrock/Memory/`
- Update current priorities and open loops in `./bedrock/Work/`
- Run: `bedrock sync --project .`
"""

_GLOBAL_CLAUDE_SECTION = """\

<!-- bedrock-global -->
## Project Bedrock (if present)

If this project has `./bedrock/STATUS.md`:

1. Read `./bedrock/STATUS.md`
2. If `onboarding: pending` — read `AGENTS.md` and follow First-Time Onboarding
3. If `onboarding: complete` — read `./bedrock/Memory/PROJECT.md` and `./bedrock/Work/NOW.md`, then load only the relevant Memory branches

At end of session with meaningful work, update `./bedrock/Memory/`, update `./bedrock/Work/`, and run `bedrock sync --project .`
<!-- /bedrock-global -->
"""

_GLOBAL_CODEX_AGENTS_MD = """\
<!-- bedrock-global -->
# Project Bedrock (global)

If this project has `./bedrock/STATUS.md`:

1. Read `./bedrock/STATUS.md`
2. If `onboarding: pending` — read `AGENTS.md` and follow First-Time Onboarding
3. If `onboarding: complete` — read `./bedrock/Memory/PROJECT.md` and `./bedrock/Work/NOW.md`, then load only the relevant Memory branches

At end of session with meaningful work:
- Update stable project knowledge in `./bedrock/Memory/`
- Update current priorities and open loops in `./bedrock/Work/`
- Run: `bedrock sync --project .`
<!-- /bedrock-global -->
"""

_GLOBAL_GEMINI_MD = """\

<!-- bedrock-global -->
## Project Bedrock (if present)

If this project has `./bedrock/STATUS.md`:

1. Read `./bedrock/STATUS.md`
2. If `onboarding: pending` — read `AGENTS.md` and follow First-Time Onboarding
3. If `onboarding: complete` — read `./bedrock/Memory/PROJECT.md` and `./bedrock/Work/NOW.md`, then load only the relevant Memory branches

At end of session with meaningful work, update `./bedrock/Memory/`, update `./bedrock/Work/`, and run `bedrock sync --project .`
<!-- /bedrock-global -->
"""


@main.command("install-global")
@click.option("--uninstall", is_flag=True, help="Remove bedrock from global config files.")
@click.option("--dry-run", is_flag=True, help="Show what would change without writing.")
def install_global(uninstall: bool, dry_run: bool) -> None:
    """Install bedrock into global agent config (~/.cursor, ~/.claude, ~/.codex, ~/.gemini).

    Adds a lightweight conditional rule to each tool's global config so
    any project with a bedrock vault is picked up automatically — no per-project
    setup needed.

    Safe to run multiple times (idempotent). Use --uninstall to remove.
    """
    home = Path.home()
    actions: list[str] = []

    # ── Cursor: ~/.cursor/rules/bedrock-global.mdc ────────────────────────────
    cursor_rule = home / ".cursor" / "rules" / "bedrock-global.mdc"
    if uninstall:
        if cursor_rule.exists():
            if not dry_run:
                cursor_rule.unlink()
            actions.append(f"  removed: {cursor_rule}")
        else:
            actions.append(f"  skip (not installed): {cursor_rule}")
    else:
        cursor_rule.parent.mkdir(parents=True, exist_ok=True)
        if cursor_rule.exists() and _GLOBAL_SENTINEL_CURSOR in cursor_rule.read_text(encoding="utf-8"):
            actions.append(f"  up-to-date: {cursor_rule}")
        else:
            if not dry_run:
                cursor_rule.write_text(_GLOBAL_CURSOR_RULE, encoding="utf-8")
            actions.append(f"  {'[dry-run] would write' if dry_run else 'wrote'}: {cursor_rule}")

    # ── Claude Code: append section to ~/.claude/CLAUDE.md ────────────────────
    claude_md = home / ".claude" / "CLAUDE.md"
    if uninstall:
        if claude_md.exists():
            text = claude_md.read_text(encoding="utf-8")
            if _GLOBAL_SENTINEL_CLAUDE in text:
                import re as _re
                cleaned = _re.sub(
                    r"\n<!-- bedrock-global -->.*?<!-- /bedrock-global -->\n",
                    "",
                    text,
                    flags=_re.DOTALL,
                )
                if not dry_run:
                    claude_md.write_text(cleaned, encoding="utf-8")
                actions.append(f"  removed section from: {claude_md}")
            else:
                actions.append(f"  skip (not installed): {claude_md}")
        else:
            actions.append(f"  skip (file not found): {claude_md}")
    else:
        existing = claude_md.read_text(encoding="utf-8") if claude_md.exists() else ""
        if _GLOBAL_SENTINEL_CLAUDE in existing:
            actions.append(f"  up-to-date: {claude_md}")
        else:
            if not dry_run:
                claude_md.parent.mkdir(parents=True, exist_ok=True)
                with claude_md.open("a", encoding="utf-8") as f:
                    f.write(_GLOBAL_CLAUDE_SECTION)
            actions.append(f"  {'[dry-run] would append' if dry_run else 'appended'}: {claude_md}")

    # ── Codex: ~/.codex/AGENTS.md ─────────────────────────────────────────────
    codex_agents = home / ".codex" / "AGENTS.md"
    if uninstall:
        if codex_agents.exists():
            text = codex_agents.read_text(encoding="utf-8")
            if _GLOBAL_SENTINEL_CODEX in text:
                import re as _re2
                cleaned = _re2.sub(
                    r"<!-- bedrock-global -->.*?<!-- /bedrock-global -->\n?",
                    "",
                    text,
                    flags=_re2.DOTALL,
                ).strip()
                if not dry_run:
                    if cleaned:
                        codex_agents.write_text(cleaned + "\n", encoding="utf-8")
                    else:
                        codex_agents.unlink()
                actions.append(f"  removed section from: {codex_agents}")
            else:
                actions.append(f"  skip (not installed): {codex_agents}")
        else:
            actions.append(f"  skip (not installed): {codex_agents}")
    else:
        existing = codex_agents.read_text(encoding="utf-8") if codex_agents.exists() else ""
        if _GLOBAL_SENTINEL_CODEX in existing:
            actions.append(f"  up-to-date: {codex_agents}")
        else:
            if not dry_run:
                codex_agents.parent.mkdir(parents=True, exist_ok=True)
                with codex_agents.open("a", encoding="utf-8") as f:
                    f.write(_GLOBAL_CODEX_AGENTS_MD)
            actions.append(f"  {'[dry-run] would write' if dry_run else 'wrote'}: {codex_agents}")

    # ── Gemini CLI / Antigravity: ~/.gemini/GEMINI.md ─────────────────────────
    gemini_md = home / ".gemini" / "GEMINI.md"
    if uninstall:
        if gemini_md.exists():
            text = gemini_md.read_text(encoding="utf-8")
            if _GLOBAL_SENTINEL_GEMINI in text:
                import re as _re3
                cleaned = _re3.sub(
                    r"\n<!-- bedrock-global -->.*?<!-- /bedrock-global -->\n?",
                    "",
                    text,
                    flags=_re3.DOTALL,
                ).strip()
                if not dry_run:
                    if cleaned:
                        gemini_md.write_text(cleaned + "\n", encoding="utf-8")
                    else:
                        gemini_md.unlink()
                actions.append(f"  removed section from: {gemini_md}")
            else:
                actions.append(f"  skip (not installed): {gemini_md}")
        else:
            actions.append(f"  skip (not installed): {gemini_md}")
    else:
        existing = gemini_md.read_text(encoding="utf-8") if gemini_md.exists() else ""
        if _GLOBAL_SENTINEL_GEMINI in existing:
            actions.append(f"  up-to-date: {gemini_md}")
        else:
            if not dry_run:
                gemini_md.parent.mkdir(parents=True, exist_ok=True)
                with gemini_md.open("a", encoding="utf-8") as f:
                    f.write(_GLOBAL_GEMINI_MD)
            actions.append(f"  {'[dry-run] would append' if dry_run else 'appended'}: {gemini_md}")

    verb = "Uninstalled" if uninstall else "Installed"
    click.echo(f"{verb} bedrock global config:", err=True)
    for a in actions:
        click.echo(a, err=True)

    if not uninstall and not dry_run:
        click.echo("", err=True)
        click.echo("Bedrock will now activate in any project that has a ./bedrock/ vault.", err=True)


@main.command()
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
@click.option("--check", is_flag=True, help="Only check for updates, do not install.")
def upgrade(yes: bool, check: bool) -> None:
    """Upgrade bedrock to the latest version from PyPI."""
    import urllib.request
    import json as _json

    pypi_url = "https://pypi.org/pypi/project-bedrock/json"
    click.echo(f"Current version: {__version__}", err=True)
    click.echo("Checking PyPI...", err=True)

    try:
        with urllib.request.urlopen(pypi_url, timeout=10) as resp:
            data = _json.loads(resp.read())
        latest = data["info"]["version"]
    except Exception as exc:
        click.echo(f"Could not reach PyPI: {exc}", err=True)
        raise SystemExit(1)

    if latest == __version__:
        click.echo(f"Already up to date ({__version__}).", err=True)
        return

    click.echo(f"New version available: {latest}", err=True)

    # Warn about legacy installs that will block the upgrade from taking effect.
    from agent_knowledge.runtime.health import find_legacy_installs, detect_install_method

    legacy = find_legacy_installs()
    if legacy:
        method = detect_install_method()
        click.secho(
            "Legacy install(s) detected that can shadow this upgrade; remove them first:",
            fg="yellow",
            err=True,
        )
        for item in legacy:
            if method == "pipx":
                cmd = f"pipx uninstall {item['name']}"
            elif method == "uv":
                cmd = f"uv tool uninstall {item['name']}"
            else:
                cmd = f"{Path(sys.executable).name} -m pip uninstall -y {item['name']}"
            click.secho(f"  {item['name']} {item['version']}  ->  {cmd}", fg="yellow", err=True)
        click.echo("", err=True)

    if check:
        return

    # Detect installer. uv tool and pipx each wrap bedrock in their own venv;
    # using the wrong upgrader silently no-ops or fails, so match the source.
    import shutil

    bedrock_exe = shutil.which("bedrock") or ""
    haystack = f"{sys.executable} {bedrock_exe} {sys.prefix} {os.environ.get('PIPX_HOME', '')}".lower()
    if "pipx" in haystack:
        upgrade_cmd = ["pipx", "upgrade", "project-bedrock"]
        installer = "pipx"
    elif (os.sep + "uv" + os.sep) in haystack or "/uv/tools/" in haystack:
        upgrade_cmd = ["uv", "tool", "upgrade", "project-bedrock"]
        installer = "uv tool"
    else:
        upgrade_cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "project-bedrock"]
        installer = "pip"

    if not yes:
        click.confirm(
            f"Upgrade to {latest} using {installer}?",
            default=True,
            abort=True,
        )

    result = subprocess.run(upgrade_cmd)
    if result.returncode != 0:
        click.echo("Upgrade failed.", err=True)
        raise SystemExit(result.returncode)

    click.echo("", err=True)
    click.echo(f"Upgraded to {latest}. Run `bedrock refresh-system` to update project bridge files.", err=True)
