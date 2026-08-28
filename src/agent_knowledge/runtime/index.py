"""Progressive retrieval: knowledge index generation and search.

Three-layer retrieval model:
  Layer 1 -- compact index (JSON + markdown catalog, cheap to load)
  Layer 2 -- search / shortlist (query against index, return relevant paths)
  Layer 3 -- full note contents (load only chosen notes on demand)

The index is written to Views/graph/ by default and is never canonical.
Memory/ and Work/ notes are ranked above Evidence/ and Outputs/ in search
results.
"""

from __future__ import annotations

import datetime
import json
import re
from pathlib import Path
from typing import Any, Sequence

from .paths import is_memory_root_relpath, resolve_index_output_paths

# Folders in priority order for retrieval.
_FOLDER_ORDER = ["Memory", "Work", "Evidence", "Outputs"]
_CANONICAL_FOLDERS = {"Memory", "Work"}

# Branch entry note pattern: <topic>/<topic>.md
_BRANCH_ENTRY_RE = re.compile(r"^([^/]+)/\1\.md$")


def _extract_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    fm: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip().strip("\"'")
    return fm


def _note_title(text: str, path: Path) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem.replace("-", " ").replace("_", " ").title()


def _first_content_lines(text: str, max_chars: int = 200) -> str:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end >= 0:
            text = text[end + 4:]
    result: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped == "---":
            continue
        if stripped.startswith("|") or stripped.startswith("```"):
            continue
        # Strip wikilinks, bold, inline code for clean plain-text summary
        stripped = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", stripped)
        stripped = re.sub(r"\[\[([^\]]+)\]\]", r"\1", stripped)
        stripped = re.sub(r"\*\*(.+?)\*\*", r"\1", stripped)
        stripped = re.sub(r"`([^`]+)`", r"\1", stripped)
        stripped = stripped.strip()
        if not stripped:
            continue
        result.append(stripped)
        if sum(len(s) for s in result) >= max_chars:
            break
    summary = " ".join(result)
    return summary[:max_chars] + ("..." if len(summary) > max_chars else "")


def _is_branch_entry(rel: str) -> bool:
    return bool(_BRANCH_ENTRY_RE.match(rel)) or is_memory_root_relpath(rel)


def build_index(vault_dir: Path) -> dict[str, Any]:
    """Scan the vault and return a structured knowledge index."""
    notes: list[dict[str, Any]] = []

    for folder in _FOLDER_ORDER:
        folder_dir = vault_dir / folder
        if not folder_dir.is_dir():
            continue
        folder_canonical = folder in _CANONICAL_FOLDERS

        for md_file in sorted(folder_dir.rglob("*.md")):
            if md_file.name in {"README.md"}:
                continue
            rel = md_file.relative_to(vault_dir).as_posix()
            try:
                text = md_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            # A member's own perspective (Memory/Members/<id>/) is NOT canonical
            # team truth — surface it under its own "Members" group, non-canonical,
            # so default search ranks/filters it below consensus. Memory/Team/ and
            # the rest of Memory/ stay canonical.
            is_member_note = rel.startswith("Memory/Members/")
            canonical = folder_canonical and not is_member_note
            folder_label = "Members" if is_member_note else folder

            fm = _extract_frontmatter(text)
            notes.append(
                {
                    "path": rel,
                    "title": _note_title(text, md_file),
                    "note_type": fm.get("note_type", "unknown"),
                    "area": fm.get("area", fm.get("project", "")),
                    "canonical": canonical,
                    "folder": folder_label,
                    "is_branch_entry": _is_branch_entry(rel),
                    "summary": _first_content_lines(text),
                }
            )

    return {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "vault": str(vault_dir),
        "note_count": len(notes),
        "notes": notes,
    }


def write_index(vault_dir: Path, *, dry_run: bool = False) -> list[str]:
    """Generate the knowledge index. Returns action strings."""
    index = build_index(vault_dir)
    json_dst, md_dst = resolve_index_output_paths(vault_dir)
    rel_json = json_dst.relative_to(vault_dir).as_posix()
    rel_md = md_dst.relative_to(vault_dir).as_posix()

    if dry_run:
        return [
            f"  [dry-run] would write: {rel_json} ({index['note_count']} notes)",
            f"  [dry-run] would write: {rel_md}",
        ]

    json_dst.parent.mkdir(parents=True, exist_ok=True)
    json_dst.write_text(json.dumps(index, indent=2), encoding="utf-8")

    # Compact markdown catalog for agents and humans.
    groups: dict[str, list[dict]] = {}
    for note in index["notes"]:
        groups.setdefault(note["folder"], []).append(note)

    md_lines: list[str] = [
        "---\n",
        "note_type: output\n",
        f"generated: {index['generated']}\n",
        "canonical: false\n",
        "---\n",
        "\n",
        "# Knowledge Index\n",
        "\n",
        "> Generated output. Not canonical. Do not treat as Memory.\n",
        "\n",
        f"Generated: {index['generated']}  \n",
        f"Total notes: {index['note_count']}\n",
        "\n",
    ]
    # Render Members (perspective) right after Memory, before the rest.
    render_order = list(_FOLDER_ORDER)
    if "Members" in groups:
        render_order.insert(render_order.index("Memory") + 1, "Members")
    for folder in render_order:
        if folder not in groups:
            continue
        if folder == "Members":
            tag = "non-canonical"
        else:
            tag = "canonical" if folder in _CANONICAL_FOLDERS else "non-canonical"
        md_lines.append(f"## {folder} [{tag}]\n\n")
        for note in groups[folder]:
            entry_marker = " (branch entry)" if note["is_branch_entry"] else ""
            summary = note["summary"]
            if len(summary) > 120:
                summary = summary[:120] + "..."
            md_lines.append(f"- **{note['title']}** `{note['path']}`{entry_marker}\n")
            if summary:
                md_lines.append(f"  {summary}\n")
        md_lines.append("\n")

    md_dst.write_text("".join(md_lines), encoding="utf-8")

    return [
        f"  wrote: {rel_json} ({index['note_count']} notes)",
        f"  wrote: {rel_md}",
    ]


def search(
    vault_dir: Path,
    query: str,
    *,
    max_results: int = 10,
    include_non_canonical: bool = True,
) -> list[dict[str, Any]]:
    """Search the knowledge index for query.

    Layer 2: returns a shortlist of notes ranked by relevance.
    Memory/ notes are scored higher than Evidence/ and Outputs/.
    Branch entry notes are preferred over leaf notes within each folder.
    """
    index_path, _index_md_path = resolve_index_output_paths(vault_dir)
    if index_path.is_file():
        try:
            notes: list[dict] = json.loads(index_path.read_text(encoding="utf-8")).get("notes", [])
        except (json.JSONDecodeError, OSError):
            notes = build_index(vault_dir).get("notes", [])
    else:
        notes = build_index(vault_dir).get("notes", [])

    q = query.lower()

    def score(note: dict) -> int:
        s = 0
        if not include_non_canonical and not note.get("canonical"):
            return 0
        title = note.get("title", "").lower()
        path = note.get("path", "").lower()
        area = note.get("area", "").lower()
        summary = note.get("summary", "").lower()

        if q in title:
            s += 10
        if q in path:
            s += 5
        if q in area:
            s += 4
        if q in summary:
            s += 2
        if note.get("canonical"):
            s += 6
        if note.get("is_branch_entry"):
            s += 3
        return s

    scored = [(score(n), n) for n in notes if score(n) > 0]
    scored.sort(key=lambda x: -x[0])
    return [n for _, n in scored[:max_results]]


def load_note(vault_dir: Path, rel_path: str) -> str | None:
    """Layer 3: load full note content for a given relative path."""
    p = vault_dir / rel_path
    if not p.is_file():
        return None
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
