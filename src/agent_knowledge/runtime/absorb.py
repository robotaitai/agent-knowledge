"""Absorb existing project knowledge artifacts into the vault.

Scans the project for knowledge-bearing files (docs, ADRs, architecture notes,
changelogs, etc.) and ingests them into the vault:

  Evidence/imports/  -- raw copies with metadata header (non-canonical)
  Memory/decisions/  -- structured ADR/decision records parsed into decisions.md
  History/           -- absorb events appended to events.ndjson

The CLI does the mechanical import. The agent reads the manifest and decides
what deserves promotion to Memory/ branches.

Design rules:
- File-based, no database, no service required
- Evidence/imports copies are non-canonical; never auto-promote to Memory/
- Idempotent: skip files already present in Evidence/imports/
- Respect .agentknowledgeignore patterns
- Decision files that match ADR format are parsed into decisions.md
"""

from __future__ import annotations

import datetime
import json
import re
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Source discovery
# ---------------------------------------------------------------------------

_ROOT_DOC_NAMES = {
    "ARCHITECTURE.md",
    "CHANGELOG.md",
    "DESIGN.md",
    "CONTRIBUTING.md",
    "HISTORY.md",
    "ROADMAP.md",
    "OVERVIEW.md",
    "TECHNICAL.md",
    "SPECIFICATION.md",
    "SPEC.md",
    "API.md",
    "DEVELOPMENT.md",
    "ONBOARDING.md",
}

_SKIP_ROOT_NAMES = {
    "AGENTS.md",
    "CLAUDE.md",
    "README.md",
    ".agentknowledgeignore",
}

_DOC_DIR_NAMES = {"docs", "doc", "documentation", "wiki", "guides", "guide"}

_ADR_DIR_NAMES = {
    "adr",
    "ADR",
    "decisions",
    "adrs",
    "docs/adr",
    "docs/decisions",
    "docs/ADR",
    "documentation/adr",
    "documentation/decisions",
}


def _load_ignores(repo_root: Path) -> set[str]:
    ignore_file = repo_root / ".agentknowledgeignore"
    if not ignore_file.is_file():
        return set()
    lines = ignore_file.read_text().splitlines()
    return {l.strip() for l in lines if l.strip() and not l.startswith("#")}


def _is_ignored(path: Path, repo_root: Path, ignores: set[str]) -> bool:
    rel = str(path.relative_to(repo_root))
    for pattern in ignores:
        if pattern in rel or rel.startswith(pattern.lstrip("/")):
            return True
    return False


def _vault_prefix(repo_root: Path) -> str:
    vault = repo_root / "agent-knowledge"
    if vault.is_symlink() or vault.is_dir():
        try:
            return str(vault.resolve())
        except Exception:
            pass
    return str(vault)


def discover_sources(repo_root: Path) -> list[dict[str, Any]]:
    """Find knowledge-bearing files in the project."""
    ignores = _load_ignores(repo_root)
    vault_real = _vault_prefix(repo_root)
    sources: list[dict[str, Any]] = []
    seen: set[Path] = set()

    def _add(path: Path, category: str) -> None:
        rp = path.resolve()
        if rp in seen:
            return
        # Skip anything inside the vault itself
        if str(rp).startswith(vault_real):
            return
        if _is_ignored(path, repo_root, ignores):
            return
        seen.add(rp)
        sources.append({"path": path, "category": category})

    # Known root-level doc files
    for name in _ROOT_DOC_NAMES:
        candidate = repo_root / name
        if candidate.is_file():
            _add(candidate, "root-doc")

    # Any other root-level *.md not in skip list
    for f in sorted(repo_root.glob("*.md")):
        if f.name not in _SKIP_ROOT_NAMES and f.name not in _ROOT_DOC_NAMES:
            _add(f, "root-doc")

    # docs/ and similar documentation directories
    for dir_name in sorted(_DOC_DIR_NAMES):
        doc_dir = repo_root / dir_name
        if doc_dir.is_dir():
            for f in sorted(doc_dir.rglob("*.md")):
                _add(f, "documentation")

    # ADR / decision directories
    for dir_name in sorted(_ADR_DIR_NAMES):
        adr_dir = repo_root / dir_name
        if adr_dir.is_dir():
            for f in sorted(adr_dir.rglob("*.md")):
                _add(f, "decision")

    return sources


# ---------------------------------------------------------------------------
# ADR / decision parsing
# ---------------------------------------------------------------------------

_ADR_TITLE_RE = re.compile(r"^#\s+(?:ADR[- ]?\d+[:\s]+)?(.+)", re.MULTILINE)
_ADR_STATUS_RE = re.compile(r"##\s+Status\s*\n+(.+?)(?:\n\n|\n##)", re.DOTALL | re.IGNORECASE)
_ADR_CONTEXT_RE = re.compile(r"##\s+(?:Context|Problem)\s*\n+(.+?)(?:\n##|\Z)", re.DOTALL | re.IGNORECASE)


def _looks_like_adr(content: str) -> bool:
    """Check if a file looks like an ADR / decision record."""
    has_status = bool(re.search(r"##\s+Status", content, re.IGNORECASE))
    has_decision = bool(re.search(r"##\s+(?:Decision|Context|Problem)", content, re.IGNORECASE))
    return has_status or has_decision


def _parse_adr(path: Path, content: str) -> dict[str, str] | None:
    title_m = _ADR_TITLE_RE.search(content)
    title = title_m.group(1).strip() if title_m else path.stem.replace("-", " ").replace("_", " ").title()
    status_m = _ADR_STATUS_RE.search(content)
    status = status_m.group(1).strip().splitlines()[0].strip() if status_m else "unknown"
    context_m = _ADR_CONTEXT_RE.search(content)
    context_snippet = context_m.group(1).strip()[:200].replace("\n", " ") if context_m else ""
    return {"title": title, "status": status.lower(), "context": context_snippet}


# ---------------------------------------------------------------------------
# Evidence/imports ingestion
# ---------------------------------------------------------------------------

_EVIDENCE_FRONT = """\
---
source: {rel_path}
category: {category}
imported: {date}
canonical: false
---

"""


def _import_to_evidence(
    src_path: Path,
    vault_dir: Path,
    repo_root: Path,
    category: str,
    *,
    dry_run: bool,
) -> dict[str, Any]:
    rel_path = src_path.relative_to(repo_root)
    # Flatten path into a single filename to avoid directory collisions
    import_name = str(rel_path).replace("/", "__").replace("\\", "__")
    if not import_name.endswith(".md"):
        import_name += ".md"
    dst = vault_dir / "Evidence" / "imports" / import_name

    if dst.exists():
        return {"path": str(rel_path), "action": "exists", "dest": str(dst.relative_to(vault_dir))}

    if dry_run:
        return {"path": str(rel_path), "action": "would-import", "dest": str(dst.relative_to(vault_dir))}

    content = src_path.read_text(errors="replace")
    header = _EVIDENCE_FRONT.format(
        rel_path=rel_path,
        category=category,
        date=datetime.date.today().isoformat(),
    )
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(header + content)
    return {"path": str(rel_path), "action": "imported", "dest": str(dst.relative_to(vault_dir))}


# ---------------------------------------------------------------------------
# Decision ingestion
# ---------------------------------------------------------------------------

def _append_decision(
    decisions_path: Path,
    title: str,
    status: str,
    context: str,
    source_path: str,
    *,
    dry_run: bool,
) -> bool:
    """Append a parsed ADR to decisions.md. Returns True if written."""
    content = decisions_path.read_text() if decisions_path.is_file() else ""
    # Avoid duplicates: skip if source path already mentioned
    if source_path in content:
        return False

    date = datetime.date.today().isoformat()
    entry = (
        f"\n"
        f"- **date**: {date}\n"
        f"  **title**: {title}\n"
        f"  **status**: {status}\n"
        f"  **source**: {source_path}\n"
    )
    if context:
        entry += f"  **context**: {context}\n"

    if dry_run:
        return True  # Would append

    decisions_path.parent.mkdir(parents=True, exist_ok=True)
    if not decisions_path.is_file():
        decisions_path.write_text(
            "---\narea: decisions\nupdated: "
            + date
            + "\n---\n\n# Decisions\n"
        )
    with open(decisions_path, "a") as f:
        f.write(entry)
    return True


# ---------------------------------------------------------------------------
# Manifest generation
# ---------------------------------------------------------------------------

_MANIFEST_TEMPLATE = """\
---
generated: {date}
canonical: false
---

# Absorb Manifest

Generated by `agent-knowledge absorb` on {date}.
This is a non-canonical summary of what was ingested. The agent should review
and promote relevant content to `Memory/` branches.

## Sources found: {total}

| File | Category | Action |
|------|----------|--------|
{rows}

## Decisions parsed: {decisions_parsed}

{decision_notes}

## Next steps for the agent

1. Review imported files in `Evidence/imports/`
2. For each imported doc, extract stable facts and write to the relevant `Memory/<branch>.md`
3. For parsed decisions, verify they are captured in `Memory/decisions/decisions.md`
4. Run `/memory-update` to sync and summarize changes
"""


def _write_manifest(
    vault_dir: Path,
    results: list[dict[str, Any]],
    decisions_written: list[str],
    *,
    dry_run: bool,
) -> Path:
    date = datetime.date.today().isoformat()
    rows = "\n".join(
        f"| `{r['path']}` | {r.get('category', '')} | {r['action']} |"
        for r in results
    )
    decision_notes = (
        "\n".join(f"- `{d}`" for d in decisions_written)
        if decisions_written
        else "_None detected._"
    )
    content = _MANIFEST_TEMPLATE.format(
        date=date,
        total=len(results),
        rows=rows or "_None_",
        decisions_parsed=len(decisions_written),
        decision_notes=decision_notes,
    )
    manifest_path = vault_dir / "Outputs" / "absorb-manifest.md"
    if not dry_run:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(content)
    return manifest_path


# ---------------------------------------------------------------------------
# History event
# ---------------------------------------------------------------------------

def _append_history_event(
    vault_dir: Path,
    project_slug: str,
    imported: int,
    decisions_parsed: int,
    touched_paths: list[str],
) -> None:
    events_path = vault_dir / "History" / "events.ndjson"
    if not events_path.is_file():
        return
    event = {
        "timestamp": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "event_type": "absorb",
        "source_tool": "cli",
        "project_slug": project_slug,
        "summary": f"Absorbed {imported} docs, {decisions_parsed} decisions from project files",
        "touched_paths": touched_paths[:20],
        "touched_branches": [],
        "related_notes": [],
        "related_decisions": [],
        "related_commits": [],
        "confidence": "high",
    }
    events_path.parent.mkdir(parents=True, exist_ok=True)
    with open(events_path, "a") as f:
        f.write(json.dumps(event) + "\n")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_absorb(
    repo_root: Path,
    vault_dir: Path,
    project_slug: str,
    *,
    dry_run: bool = False,
    include_decisions: bool = True,
) -> dict[str, Any]:
    """Main absorb pipeline.

    Returns a summary dict with counts and per-file results.
    """
    sources = discover_sources(repo_root)

    results: list[dict[str, Any]] = []
    decisions_written: list[str] = []

    decisions_path = vault_dir / "Memory" / "decisions" / "decisions.md"

    for source in sources:
        path: Path = source["path"]
        category: str = source["category"]

        # Always ingest to Evidence/imports/
        result = _import_to_evidence(path, vault_dir, repo_root, category, dry_run=dry_run)
        result["category"] = category
        results.append(result)

        # For decision/ADR files, also parse into decisions.md
        if include_decisions and category == "decision":
            try:
                content = path.read_text(errors="replace")
            except Exception:
                continue
            if _looks_like_adr(content):
                parsed = _parse_adr(path, content)
                if parsed:
                    rel = str(path.relative_to(repo_root))
                    written = _append_decision(
                        decisions_path,
                        title=parsed["title"],
                        status=parsed["status"],
                        context=parsed["context"],
                        source_path=rel,
                        dry_run=dry_run,
                    )
                    if written:
                        decisions_written.append(rel)

    manifest_path = _write_manifest(vault_dir, results, decisions_written, dry_run=dry_run)

    imported = sum(1 for r in results if r["action"] == "imported")
    already_present = sum(1 for r in results if r["action"] == "exists")

    if not dry_run and imported > 0:
        touched = [r["path"] for r in results if r["action"] == "imported"]
        _append_history_event(vault_dir, project_slug, imported, len(decisions_written), touched)

    return {
        "sources_found": len(sources),
        "imported": imported,
        "already_present": already_present,
        "decisions_parsed": len(decisions_written),
        "manifest": str(manifest_path.relative_to(vault_dir)) if not dry_run else "Outputs/absorb-manifest.md",
        "dry_run": dry_run,
        "results": results,
    }
