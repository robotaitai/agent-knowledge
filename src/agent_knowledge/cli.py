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


# -- helpers --------------------------------------------------------------- #

_LOCAL_GITIGNORE_BLOCK = """\
# agent-knowledge: noisy auto-generated content excluded from git
# Curated knowledge (Memory/, History/, Evidence/imports/, Dashboards/) IS tracked.
agent-knowledge/Evidence/raw/
agent-knowledge/Evidence/captures/
agent-knowledge/Outputs/site/
agent-knowledge/Outputs/graph.json
agent-knowledge/Outputs/knowledge-index.json
agent-knowledge/Outputs/knowledge-index.md
agent-knowledge/Outputs/absorb-manifest.md
agent-knowledge/.obsidian/workspace
agent-knowledge/.obsidian/workspace.json
agent-knowledge/.obsidian/workspaces.json
"""

_LOCAL_GITIGNORE_SENTINEL = "agent-knowledge/Evidence/raw/"


def _patch_gitignore_for_local_knowledge(repo_path: Path, json_mode: bool) -> None:
    """Append local-mode knowledge gitignore patterns if not already present."""
    gitignore = repo_path / ".gitignore"
    if gitignore.exists():
        content = gitignore.read_text()
        if _LOCAL_GITIGNORE_SENTINEL in content:
            return  # already patched
        gitignore.write_text(content.rstrip("\n") + "\n\n" + _LOCAL_GITIGNORE_BLOCK)
    else:
        gitignore.write_text(_LOCAL_GITIGNORE_BLOCK)
    if not json_mode:
        click.echo("  .gitignore: added local knowledge patterns", err=True)


# -- init ------------------------------------------------------------------ #


@main.command()
@click.option("--slug", default=None, help="Project slug (default: repo directory name).")
@click.option("--repo", default=".", type=click.Path(exists=True), help="Project repo path (default: cwd).")
@click.option("--knowledge-home", default=None, help="Knowledge root (default: $AGENT_KNOWLEDGE_HOME or ~/agent-os/projects).")
@click.option("--real-path", default=None, help="Explicit external knowledge folder path.")
@click.option("--local", "local_mode", is_flag=True, help="Store knowledge inside the repo (git-tracked). ~/agent-os symlink points back to the repo folder.")
@click.option("--no-integrations", is_flag=True, help="Skip auto-detection and installation of tool integrations.")
@click.option("--dry-run", is_flag=True, help="Preview changes without writing.")
@click.option("--json", "json_mode", is_flag=True, help="Output JSON only.")
@click.option("--force", is_flag=True, help="Overwrite existing files.")
def init(
    slug: str | None,
    repo: str,
    knowledge_home: str | None,
    real_path: str | None,
    local_mode: bool,
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
      default   Knowledge lives in ~/agent-os/projects/<slug>/ (external vault).
                ./agent-knowledge is a symlink to that folder.
      --local   Knowledge lives in ./agent-knowledge/ inside the repo (git-tracked).
                ~/agent-os/projects/<slug>/ is a symlink back to the repo folder.
                Noisy subfolders (Evidence/raw, Evidence/captures) are added
                to .gitignore automatically.
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
    if local_mode:
        args.append("--local")
    args.append("--install-hooks")
    _add_common_flags(args, dry_run=dry_run, json_mode=json_mode, force=force)
    rc = run_bash_script("install-project-links.sh", args)
    if rc != 0:
        sys.exit(rc)

    # In local mode, patch .gitignore to exclude noisy knowledge subfolders
    if local_mode and not dry_run:
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

        vault_dir = repo_path / "agent-knowledge"
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
        prompt = "Read AGENTS.md and ./agent-knowledge/STATUS.md, then onboard this project."
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


_REPO_URL = "https://github.com/robotaitai/agent-knowledge"
_STAR_MARKER = Path.home() / ".agent-knowledge-starred"


def _maybe_star() -> None:
    """Prompt to star the repo once, then never again. Skips in non-interactive shells."""
    if _STAR_MARKER.exists():
        return
    if not sys.stderr.isatty():
        return
    try:
        click.echo("", err=True)
        if click.confirm(
            click.style("Like agent-knowledge? Star it on GitHub", fg="yellow"),
            default=True,
            err=True,
        ):
            import webbrowser

            webbrowser.open(_REPO_URL)
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
      1. Copy agent_docs/memory/*.md -> agent-knowledge/Memory/ (newer only)
      2. Extract recent git log into Evidence/raw/git-recent.md
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
    """Validate setup, pointer resolution, and note structure.

    Reports whether the project integration is stale and suggests
    `agent-knowledge refresh-system` when the framework version has changed.
    """
    from agent_knowledge.runtime.refresh import is_stale, check_cursor_integration, check_claude_integration
    from agent_knowledge.runtime.history import history_exists

    repo_root = Path(project).resolve()

    # Framework version staleness check
    stale, prior, current = is_stale(repo_root)
    if stale and not json_mode:
        if prior:
            click.secho(
                f"Warning: project integration is at v{prior}, installed framework is v{current}. "
                f"Run: agent-knowledge refresh-system",
                fg="yellow",
                err=True,
            )
        else:
            click.secho(
                f"Warning: no framework_version in STATUS.md. "
                f"Run: agent-knowledge refresh-system",
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
    vault_dir = repo_root / "agent-knowledge"
    if vault_dir.is_dir() and not history_exists(vault_dir) and not json_mode:
        click.secho(
            "Note: no History/ layer found. Run: agent-knowledge backfill-history",
            fg="cyan",
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
    Layer 1: loads the compact index (Outputs/knowledge-index.json).
    Layer 2: returns a ranked shortlist of relevant notes.
    Layer 3: use --full or read the note files directly for full content.
    """
    import json as json_mod

    from agent_knowledge.runtime.index import search as idx_search

    vault = Path(project).resolve() / "agent-knowledge"
    if not vault.is_dir():
        click.echo("No agent-knowledge vault found. Run: agent-knowledge init", err=True)
        sys.exit(1)

    if not query:
        click.echo("Usage: agent-knowledge search <query>", err=True)
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
    """Regenerate the knowledge index in Outputs/.

    Produces Outputs/knowledge-index.json (machine-readable) and
    Outputs/knowledge-index.md (compact human/agent catalog).
    The index is non-canonical output -- not curated memory.
    """
    import json as json_mod

    from agent_knowledge.runtime.index import write_index

    vault = Path(project).resolve() / "agent-knowledge"
    if not vault.is_dir():
        click.echo("No agent-knowledge vault found. Run: agent-knowledge init", err=True)
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
@click.option("--output-dir", default=None, type=click.Path(), help="Output directory (default: Outputs/site/).")
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

    Generates Outputs/site/index.html and Outputs/site/data/knowledge.json.
    Opens in any browser without Obsidian. Memory/ is primary; Evidence/ and
    Outputs/ are clearly marked non-canonical.

    \b
    Examples:
      agent-knowledge export-html
      agent-knowledge export-html --open
      agent-knowledge export-html --dry-run
      agent-knowledge export-html --no-evidence
    """
    import json as json_mod

    from agent_knowledge.runtime.site import generate_site

    vault = Path(project).resolve() / "agent-knowledge"
    if not vault.is_dir():
        click.echo("No agent-knowledge vault found. Run: agent-knowledge init", err=True)
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
            import webbrowser
            webbrowser.open(Path(result["index_html"]).as_uri())


# -- view ------------------------------------------------------------------ #


@main.command()
@click.option("--project", default=".", type=click.Path(exists=True), help="Project repo root.")
@click.option("--output-dir", default=None, type=click.Path(), help="Override output directory for the site.")
def view(project: str, output_dir: str | None) -> None:
    """Build the knowledge site and open it in the browser.

    Equivalent to export-html --open. No Obsidian required.
    The site is generated into Outputs/site/ and opened via file://.
    """
    import webbrowser

    from agent_knowledge.runtime.site import generate_site

    vault = Path(project).resolve() / "agent-knowledge"
    if not vault.is_dir():
        click.echo("No agent-knowledge vault found. Run: agent-knowledge init", err=True)
        sys.exit(1)

    out_dir = Path(output_dir).resolve() if output_dir else None
    result = generate_site(vault, out_dir)
    click.echo(f"{result['action']}: {result['site_dir']}", err=True)
    webbrowser.open(Path(result["index_html"]).as_uri())


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
      agent-knowledge clean-import https://docs.example.com/api
      agent-knowledge clean-import page.html --slug api-ref-2025-01-15
      agent-knowledge clean-import https://... --dry-run
    """
    import json as json_mod

    from agent_knowledge.runtime.importer import clean_import as do_import

    vault = Path(project).resolve() / "agent-knowledge"
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


@main.command("export-canvas")
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

    vault = Path(project).resolve() / "agent-knowledge"
    if not vault.is_dir():
        click.echo("No agent-knowledge vault found. Run: agent-knowledge init", err=True)
        sys.exit(1)

    out_path = Path(output).resolve() if output else None
    path, action = do_export(vault, out_path, dry_run=dry_run)

    if dry_run:
        click.echo(f"[dry-run] would write: {path}", err=True)
    else:
        click.echo(f"{action}: {path}", err=True)
        click.echo("  Open in Obsidian: Core plugins > Canvas", err=True)


# -- backfill-history ------------------------------------------------------ #


@main.command("backfill-history")
@click.option("--project", default=".", type=click.Path(exists=True), help="Project repo root.")
@click.option("--dry-run", is_flag=True, help="Preview what would be written without writing.")
@click.option("--json", "json_mode", is_flag=True, help="Output JSON summary only.")
@click.option("--force", is_flag=True, hidden=True, help="Re-run even if up to date.")
def backfill_history(project: str, dry_run: bool, json_mode: bool, force: bool) -> None:
    """Backfill lightweight project history from git and integration artifacts.

    Creates History/events.ndjson, History/history.md, and a compact timeline
    note. Runs automatically during `agent-knowledge init` on existing repos.

    History records what happened over time (milestones, releases, integrations)
    without replacing Memory/ or duplicating git. Safe to run multiple times.

    \b
    Examples:
      agent-knowledge backfill-history
      agent-knowledge backfill-history --dry-run
      agent-knowledge backfill-history --json
    """
    import json as json_mod

    from agent_knowledge.runtime.history import run_backfill

    repo_root = Path(project).resolve()
    vault_dir = repo_root / "agent-knowledge"

    if not vault_dir.is_dir():
        msg = {"error": "No agent-knowledge vault found. Run: agent-knowledge init"}
        if json_mode:
            click.echo(json_mod.dumps(msg))
        else:
            click.secho(msg["error"], fg="red", err=True)
        raise SystemExit(1)

    slug = repo_root.name
    yaml_path = repo_root / ".agent-project.yaml"
    if yaml_path.is_file():
        for line in yaml_path.read_text(errors="replace").splitlines():
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
      - Memory/decisions/decisions.md  -- parsed ADR entries appended
      - Outputs/absorb-manifest.md  -- manifest listing all imports
      - History/events.ndjson  -- absorb event recorded
    """
    from agent_knowledge.runtime.absorb import run_absorb

    repo_path = Path(project).resolve()
    vault_dir = repo_path / "agent-knowledge"

    if not vault_dir.exists():
        if json_mode:
            click.echo(
                __import__("json").dumps({"error": "agent-knowledge vault not found; run: agent-knowledge init"}),
                err=False,
            )
        else:
            click.secho("Error: agent-knowledge vault not found. Run: agent-knowledge init", fg="red", err=True)
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
        click.echo(f"  Decisions: {decisions} ADR entries parsed -> Memory/decisions/decisions.md", err=True)
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
    Safe to run after `pip install -U agent-knowledge-cli`.

    \b
    Examples:
      agent-knowledge refresh-system
      agent-knowledge refresh-system --dry-run
      agent-knowledge refresh-system --json
    """
    import json as json_mod

    from agent_knowledge.runtime.refresh import run_refresh

    repo_root = Path(project).resolve()
    result = run_refresh(repo_root, dry_run=dry_run, force=force)

    if json_mode:
        click.echo(json_mod.dumps(result, indent=2))
        return

    action = result["action"]
    version = result["framework_version"]
    prior = result.get("prior_version")
    changes = result.get("changes", [])
    warnings = result.get("warnings", [])

    if not dry_run:
        if action == "up-to-date":
            click.secho(f"Up to date. (framework v{version})", bold=True, err=True)
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

    if warnings:
        click.echo("", err=True)
        for w in warnings:
            click.secho(f"Warning: {w}", fg="yellow", err=True)

    click.echo("", err=True)
    if not dry_run and action not in ("up-to-date",):
        click.echo("Next: agent-knowledge doctor --project .", err=True)


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


@main.command(name="migrate-to-local")
@click.option("--project", default=".", type=click.Path(exists=True), help="Project repo root (default: cwd).")
@click.option("--knowledge-home", default=None, help="agent-os home for reversed symlink (default: ~/agent-os/projects).")
@click.option("--dry-run", is_flag=True, help="Preview changes without writing.")
def migrate_to_local(project: str, knowledge_home: str | None, dry_run: bool) -> None:
    """Convert an existing external-vault project to local (in-repo) knowledge storage.

    \b
    What this does:
      1. Reads the current external vault path from ./agent-knowledge (symlink).
      2. Copies all vault content into ./agent-knowledge/ (real directory).
      3. Removes the old symlink and replaces it with the real directory.
      4. Creates ~/agent-os/projects/<slug>/ as a symlink back to ./agent-knowledge/.
      5. Updates .agent-project.yaml to set vault_mode: local.
      6. Patches .gitignore with noisy-subfolder exclusions.
    """
    import re as _re
    import shutil

    repo_path = Path(project).resolve()
    pointer = repo_path / "agent-knowledge"

    if not pointer.exists() and not pointer.is_symlink():
        click.echo("Error: ./agent-knowledge does not exist in this project.", err=True)
        sys.exit(1)

    if pointer.exists() and not pointer.is_symlink():
        click.echo("Already in local mode (./agent-knowledge is a real directory).", err=True)
        sys.exit(0)

    external_vault = pointer.resolve()
    click.echo(f"Current vault: {external_vault}", err=True)
    click.echo(f"Target:        {pointer} (real directory)", err=True)

    if dry_run:
        click.echo("(dry-run) would copy vault content and swap pointer", err=True)
        return

    # Copy external vault content to a temp location, then swap
    tmp = repo_path / ".agent-knowledge-migrating"
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
            m = _re.search(r"^\s*slug:\s*(\S+)", project_yaml.read_text(), _re.MULTILINE)
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
            text = project_yaml.read_text()
            if "vault_mode:" in text:
                text = _re.sub(r"vault_mode:\s*\S+", "vault_mode: local", text)
            else:
                text = text.replace(
                    "pointer_path:", "vault_mode: local\n  pointer_path:", 1
                )
            # Update real_path to in-repo path
            text = _re.sub(
                r"real_path:\s*\S+",
                f"real_path: {pointer}",
                text,
            )
            project_yaml.write_text(text)
            click.echo("  updated: .agent-project.yaml (vault_mode: local)", err=True)
        except Exception as e:
            click.echo(f"  warning: could not update .agent-project.yaml: {e}", err=True)

    # Patch .gitignore
    _patch_gitignore_for_local_knowledge(repo_path, json_mode=False)

    click.echo("", err=True)
    click.echo("Migration complete. The knowledge folder is now part of the repo.", err=True)
    click.echo("Commit agent-knowledge/ (excluding the patterns added to .gitignore).", err=True)


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
