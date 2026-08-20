"""Static site generation for bedrock vaults.

Pipeline:
  1. build_site_data()  -> structured dict (knowledge.json)
  2. build_graph_data() -> graph nodes/edges (graph.json)
  3. Write Views/site/data/knowledge.json
  4. Write Views/site/data/graph.json
  5. _render_html()     -> complete index.html with both data sets embedded
  6. Write Views/site/index.html

Generated output is non-canonical. Memory/ remains the source of truth.
The site is a presentation layer, not the authoritative knowledge store.
The graph is a secondary discovery view inside the generated site.
"""

from __future__ import annotations

import datetime
import html as html_mod
import json
import re
from pathlib import Path
from typing import Any

from .index import (
    _CANONICAL_FOLDERS,
    _FOLDER_ORDER,
    _extract_frontmatter,
    _first_content_lines,
    _note_title,
    build_index,
)
from .paths import is_memory_root_relpath, resolve_memory_root, resolve_site_output_dir

_SITE_SCHEMA_VERSION = "1"


# --------------------------------------------------------------------------- #
# Section extraction                                                           #
# --------------------------------------------------------------------------- #


def _extract_section(text: str, name: str) -> str:
    """Extract body of a markdown ## section (everything until the next ##)."""
    pattern = rf"^##\s+{re.escape(name)}\s*$(.+?)(?=^##|\Z)"
    m = re.search(pattern, text, re.MULTILINE | re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else ""


def _parse_bullets(text: str, section_name: str) -> list[str]:
    """Return bullet items from a named section as a plain list of strings."""
    section = _extract_section(text, section_name)
    items: list[str] = []
    for line in section.splitlines():
        s = line.strip()
        if s.startswith(("- ", "* ")):
            items.append(s[2:].strip())
        elif s.startswith("+ "):
            items.append(s[2:].strip())
    return items


def _parse_recent_changes(text: str) -> list[dict[str, str]]:
    """Parse the Recent Changes section into structured dicts."""
    section = _extract_section(text, "Recent Changes")
    items: list[dict[str, str]] = []
    pattern = re.compile(r"[-*]\s+(\d{4}-\d{2}-\d{2})\s*[-:—–]\s*(.+)")
    for line in section.splitlines():
        m = pattern.match(line.strip())
        if m:
            items.append({"date": m.group(1), "text": m.group(2).strip()})
    return items


def _strip_frontmatter(text: str) -> str:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end >= 0:
            return text[end + 4:].lstrip("\n")
    return text


def _strip_md_for_summary(text: str) -> str:
    """Strip markdown syntax from text intended for use as a plain-text summary.

    Removes: wikilinks, bold/italic, inline code, table rows, headings markers,
    code fences, and horizontal rules. Returns clean readable prose.
    """
    lines = []
    for line in text.splitlines():
        s = line.strip()
        # Skip table rows, code fences, horizontal rules, headings
        if s.startswith("|") or s.startswith("```") or s.startswith("---") or s.startswith("#"):
            continue
        if re.match(r"^[*_-]{3,}$", s):
            continue
        # Replace wikilinks [[target|display]] → display, [[target]] → target
        s = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", s)
        s = re.sub(r"\[\[([^\]]+)\]\]", r"\1", s)
        # Strip bold/italic
        s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
        s = re.sub(r"__(.+?)__", r"\1", s)
        s = re.sub(r"\*(.+?)\*", r"\1", s)
        s = re.sub(r"_(.+?)_", r"\1", s)
        # Strip inline code backticks
        s = re.sub(r"`([^`]+)`", r"\1", s)
        # Strip markdown links [text](url) → text
        s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
        s = s.strip()
        if s:
            lines.append(s)
    return " ".join(lines)


# --------------------------------------------------------------------------- #
# Minimal markdown → HTML (no external deps)                                  #
# --------------------------------------------------------------------------- #


def _slugify(text: str) -> str:
    """Convert heading text to a URL-safe id (strip emojis and special chars)."""
    s = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip().lower()
    return re.sub(r"[\s_-]+", "-", s) or "section"


def _md_to_html(text: str) -> str:
    """Minimal markdown-to-HTML for note rendering in the generated site."""
    text = _strip_frontmatter(text)
    lines = text.split("\n")
    out: list[str] = []
    in_code = False
    in_ul = False
    in_ol = False
    code_buf: list[str] = []
    code_lang = ""
    toc_items: list[tuple[int, str, str]] = []  # (level, text, slug)
    slug_counts: dict[str, int] = {}

    def flush_list() -> None:
        nonlocal in_ul, in_ol
        if in_ul:
            out.append("</ul>")
            in_ul = False
        if in_ol:
            out.append("</ol>")
            in_ol = False

    def inline(s: str) -> str:
        s = html_mod.escape(s)
        # Bold
        s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"__(.+?)__", r"<strong>\1</strong>", s)
        # Italic
        s = re.sub(r"\*(.+?)\*", r"<em>\1</em>", s)
        s = re.sub(r"_(.+?)_", r"<em>\1</em>", s)
        # Inline code
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        # Links
        s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
        # Wiki-links → internal site links resolved at runtime by JS
        s = re.sub(
            r"\[\[([^\]|#]+)(?:#[^\]|]*)?\|([^\]]+)\]\]",
            lambda m: f'<a class="wikilink" data-target="{html_mod.escape(m.group(1).strip())}">{html_mod.escape(m.group(2).strip())}</a>',
            s,
        )
        s = re.sub(
            r"\[\[([^\]|#]+)(?:#[^\]]+)?\]\]",
            lambda m: f'<a class="wikilink" data-target="{html_mod.escape(m.group(1).strip())}">{html_mod.escape(m.group(1).strip())}</a>',
            s,
        )
        return s

    in_table = False
    table_rows: list[list[str]] = []
    table_header_done = False

    def flush_table() -> None:
        nonlocal in_table, table_rows, table_header_done
        if not in_table:
            return
        in_table = False
        if not table_rows:
            table_header_done = False
            return
        out.append('<table>')
        for i, row in enumerate(table_rows):
            tag = 'th' if i == 0 else 'td'
            out.append('<tr>' + ''.join(f'<{tag}>{inline(cell.strip())}</{tag}>' for cell in row) + '</tr>')
        out.append('</table>')
        table_rows = []
        table_header_done = False

    def _is_separator_row(s: str) -> bool:
        return bool(re.match(r'^\|[\s\-:|]+\|[\s\-:|]*$', s))

    def _parse_table_row(s: str) -> list[str]:
        s = s.strip()
        if s.startswith('|'):
            s = s[1:]
        if s.endswith('|'):
            s = s[:-1]
        return s.split('|')

    for line in lines:
        if line.startswith("```"):
            flush_list()
            flush_table()
            if in_code:
                if code_lang == "mermaid":
                    diagram = "\n".join(code_buf)
                    out.append(f'<div class="mermaid">{diagram}</div>')
                else:
                    out.append(html_mod.escape("\n".join(code_buf)))
                    out.append("</code></pre>")
                code_buf = []
                in_code = False
                code_lang = ""
            else:
                code_lang = line[3:].strip()
                if code_lang != "mermaid":
                    cls = f' class="language-{code_lang}"' if code_lang else ""
                    out.append(f'<pre><code{cls}>')
                in_code = True
            continue

        if in_code:
            code_buf.append(line)
            continue

        # Table rows
        if line.startswith("|"):
            flush_list()
            if _is_separator_row(line):
                table_header_done = True
                in_table = True
                continue
            in_table = True
            if not table_header_done or not table_rows:
                table_rows.append(_parse_table_row(line))
            else:
                table_rows.append(_parse_table_row(line))
            continue

        # Non-table line: flush any open table first
        if in_table:
            flush_table()

        if re.match(r"^#{1,6}\s", line):
            flush_list()
            level = len(re.match(r"^(#+)", line).group(1))
            content = line.lstrip("#").strip()
            slug_base = _slugify(content)
            slug_counts[slug_base] = slug_counts.get(slug_base, 0) + 1
            slug = slug_base if slug_counts[slug_base] == 1 else f"{slug_base}-{slug_counts[slug_base]}"
            if level in (2, 3):
                toc_items.append((level, content, slug))
            out.append(f'<h{level} id="{slug}"><a class="anchor" href="#{slug}" aria-hidden="true">#</a>{inline(content)}</h{level}>')
        elif line.startswith("> "):
            flush_list()
            out.append(f"<blockquote><p>{inline(line[2:])}</p></blockquote>")
        elif re.match(r"^[-*+]\s", line):
            if not in_ul:
                flush_list()
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{inline(line[2:])}</li>")
        elif re.match(r"^\d+\.\s", line):
            if not in_ol:
                flush_list()
                out.append("<ol>")
                in_ol = True
            stripped = re.sub(r'^\d+\.\s+', '', line)
            out.append(f"<li>{inline(stripped)}</li>")
        elif re.match(r"^---+$", line.strip()) or re.match(r"^\*\*\*+$", line.strip()):
            flush_list()
            out.append("<hr>")
        elif line.strip() == "":
            flush_list()
            out.append("")
        else:
            flush_list()
            out.append(f"<p>{inline(line)}</p>")

    flush_list()
    flush_table()
    if in_code and code_buf:
        out.append(html_mod.escape("\n".join(code_buf)))
        out.append("</code></pre>")

    body = "\n".join(out)

    if len(toc_items) >= 3:
        toc_lines = ['<nav class="toc"><div class="toc-title">Contents</div><ul>']
        for level, text, slug in toc_items:
            indent = ' style="padding-left:14px"' if level == 3 else ''
            toc_lines.append(f'<li{indent}><a href="#{html_mod.escape(slug)}">{html_mod.escape(text)}</a></li>')
        toc_lines.append('</ul></nav>')
        body = "\n".join(toc_lines) + "\n" + body

    return body


# --------------------------------------------------------------------------- #
# Data model construction                                                      #
# --------------------------------------------------------------------------- #


def _read_status(vault_dir: Path) -> dict[str, str]:
    status_file = vault_dir / "STATUS.md"
    if not status_file.is_file():
        return {}
    return _extract_frontmatter(status_file.read_text(encoding="utf-8", errors="replace"))


def _read_note(vault_dir: Path, rel_path: str) -> str:
    p = vault_dir / rel_path
    try:
        return p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""
    except OSError:
        return ""


def _build_note_data(
    vault_dir: Path,
    meta: dict[str, Any],
    *,
    include_html: bool = True,
) -> dict[str, Any]:
    """Build full data dict for a single note."""
    raw = _read_note(vault_dir, meta["path"])
    fm = _extract_frontmatter(raw)

    data: dict[str, Any] = {
        "path": meta["path"],
        "title": meta["title"],
        "folder": meta["folder"],
        "canonical": meta["canonical"],
        "note_type": meta.get("note_type", fm.get("note_type", "unknown")),
        "area": meta.get("area", fm.get("area", "")),
        "is_branch_entry": meta.get("is_branch_entry", False),
        "updated": fm.get("updated", fm.get("date", "")),
        "summary": meta.get("summary", ""),
    }

    if include_html:
        data["html"] = _md_to_html(raw)

    return data


def _build_branch_data(vault_dir: Path, meta: dict[str, Any]) -> dict[str, Any]:
    """Build rich data for a Memory branch entry note."""
    raw = _read_note(vault_dir, meta["path"])
    fm = _extract_frontmatter(raw)

    purpose = _extract_section(raw, "Purpose")
    if not purpose:
        purpose = _first_content_lines(raw, max_chars=200)

    # Build a clean plain-text summary for use in card previews
    clean_summary = _strip_md_for_summary(purpose)[:150] if purpose else ""

    return {
        "path": meta["path"],
        "title": meta["title"],
        "folder": "Memory",
        "canonical": True,
        "note_type": fm.get("note_type", "branch-entry"),
        "area": fm.get("area", meta.get("area", "")),
        "is_branch_entry": True,
        "updated": fm.get("updated", ""),
        "summary": clean_summary or meta.get("summary", ""),
        "purpose": purpose,
        "current_state": _parse_bullets(raw, "Current State"),
        "recent_changes": _parse_recent_changes(raw),
        "open_questions": _parse_bullets(raw, "Open Questions"),
        "decision_links": _parse_bullets(raw, "Decisions"),
        "leaves": [],
        "html": _md_to_html(raw),
    }


def _build_decision_data(vault_dir: Path, meta: dict[str, Any]) -> dict[str, Any]:
    """Build data for a decision file."""
    raw = _read_note(vault_dir, meta["path"])
    fm = _extract_frontmatter(raw)

    what = _extract_section(raw, "What")
    why = _extract_section(raw, "Why")

    # Derive a clean title from the filename if the heading isn't found
    title = meta["title"]
    if title.lower().startswith("decision:"):
        title = title[9:].strip()

    return {
        "path": meta["path"],
        "title": title,
        "folder": "Memory",
        "canonical": True,
        "note_type": "decision",
        "date": fm.get("date", ""),
        "status": fm.get("status", "active"),
        "what": what[:200] if what else "",
        "why": why[:200] if why else "",
        "summary": what[:120] if what else meta.get("summary", ""),
        "updated": fm.get("date", fm.get("updated", "")),
        "html": _md_to_html(raw),
    }


def build_site_data(
    vault_dir: Path,
    *,
    include_evidence: bool = True,
    include_sessions: bool = False,
) -> dict[str, Any]:
    """Build the complete site data model from the vault.

    Returns a structured dict ready to be serialized as knowledge.json.
    Memory/ is primary; Work/ is current-state context; generated and imported
    material remains non-canonical.
    """
    status = _read_status(vault_dir)
    index = build_index(vault_dir)
    all_notes = index["notes"]

    generated = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    memory_root_path = resolve_memory_root(vault_dir).relative_to(vault_dir).as_posix()

    project = {
        "name": status.get("project", vault_dir.name),
        "slug": status.get("slug", vault_dir.name),
        "profile": status.get("profile", "unknown"),
        "onboarding": status.get("onboarding", "unknown"),
        "vault_path": str(vault_dir),
        "last_updated": status.get("last_project_sync", ""),
        "memory_root_path": memory_root_path,
    }

    # --- Separate notes by folder ---
    memory_notes = [n for n in all_notes if n["folder"] == "Memory"]
    evidence_notes = [n for n in all_notes if n["folder"] == "Evidence"]
    output_notes = [n for n in all_notes if n["folder"] == "Outputs"]
    # --- Branches: Memory entry notes (excluding decisions/) ---
    branch_metas = [
        n for n in memory_notes
        if n["is_branch_entry"]
        and "decisions" not in n["path"].lower()
        and not is_memory_root_relpath(n["path"])
    ]

    # Leaf notes: non-entry Memory notes (excluding decisions/)
    leaf_metas = [
        n for n in memory_notes
        if not n["is_branch_entry"]
        and "decisions" not in n["path"].lower()
        and not is_memory_root_relpath(n["path"])
    ]

    # Flat (non-folder) Memory notes: treat as their own branch
    flat_metas = [
        n for n in memory_notes
        if not n["is_branch_entry"]
        and "decisions" not in n["path"].lower()
        and not is_memory_root_relpath(n["path"])
        and "/" not in n["path"].replace("Memory/", "", 1)
    ]

    # Build branch data
    branches: list[dict[str, Any]] = []
    for meta in branch_metas:
        branch = _build_branch_data(vault_dir, meta)
        # Attach leaves from the same folder
        branch_folder_prefix = str(Path(meta["path"]).parent.as_posix()) + "/"
        branch["leaves"] = [
            _build_note_data(vault_dir, lm)
            for lm in leaf_metas
            if lm["path"].startswith(branch_folder_prefix)
        ]
        branches.append(branch)

    # Flat notes that are not leaves of a folder-branch
    covered_paths = {b["path"] for b in branches}
    covered_paths.update(
        lf["path"] for b in branches for lf in b["leaves"]
    )
    for meta in flat_metas:
        if meta["path"] not in covered_paths:
            branches.append(_build_branch_data(vault_dir, meta))

    # Sort branches alphabetically; the memory root is handled separately.
    branches.sort(key=lambda b: b["title"])

    # --- Decisions ---
    decision_metas = [
        n for n in memory_notes
        if "decisions" in n["path"].lower()
        and n["path"] not in {"Memory/decisions.md", "Memory/decisions/decisions.md"}
    ]
    decisions = sorted(
        [_build_decision_data(vault_dir, m) for m in decision_metas],
        key=lambda d: d.get("date", ""),
        reverse=True,
    )

    # --- Global recent changes: merge across all branches, sorted ---
    all_changes: list[dict[str, str]] = []
    for branch in branches:
        for change in branch.get("recent_changes", []):
            all_changes.append({
                "date": change["date"],
                "text": change["text"],
                "branch": branch["title"],
                "branch_path": branch["path"],
            })
    all_changes.sort(key=lambda c: c["date"], reverse=True)
    recent_changes_global = all_changes[:20]

    # --- Evidence ---
    evidence: list[dict[str, Any]] = []
    if include_evidence:
        for meta in evidence_notes:
            raw = _read_note(vault_dir, meta["path"])
            fm = _extract_frontmatter(raw)
            evidence.append({
                "path": meta["path"],
                "title": meta["title"],
                "folder": "Evidence",
                "canonical": False,
                "note_type": fm.get("note_type", "evidence"),
                "source": fm.get("source", ""),
                "imported": fm.get("imported", fm.get("extracted", "")),
                "summary": meta.get("summary", ""),
                "html": _md_to_html(raw),
            })

    # --- Outputs (only list, don't embed content) ---
    outputs: list[dict[str, Any]] = []
    for meta in output_notes:
        raw = _read_note(vault_dir, meta["path"])
        fm = _extract_frontmatter(raw)
        outputs.append({
            "path": meta["path"],
            "title": meta["title"],
            "folder": "Outputs",
            "canonical": False,
            "note_type": fm.get("note_type", "output"),
            "summary": meta.get("summary", ""),
        })

    # --- Warnings ---
    warnings: list[str] = []
    status_raw_text = _read_note(vault_dir, "STATUS.md") if (vault_dir / "STATUS.md").is_file() else ""
    warn_section = _extract_section(status_raw_text, "Warnings")
    if warn_section:
        for line in warn_section.splitlines():
            s = line.strip()
            if s.startswith(("- ", "* ")):
                warnings.append(s[2:].strip())
            elif s and not s.startswith("#"):
                warnings.append(s)

    return {
        "schema": _SITE_SCHEMA_VERSION,
        "generated": generated,
        "project": project,
        "warnings": warnings,
        "branches": branches,
        "decisions": decisions,
        "recent_changes_global": recent_changes_global,
        "evidence": evidence,
        "outputs": outputs,
        "stats": {
            "branch_count": len(branches),
            "decision_count": len(decisions),
            "evidence_count": len(evidence),
            "output_count": len(outputs),
            "note_count": index["note_count"],
        },
    }


# --------------------------------------------------------------------------- #
# Graph data model                                                             #
# --------------------------------------------------------------------------- #


def build_graph_data(site_data: dict[str, Any]) -> dict[str, Any]:
    """Build graph.json from the normalized site data model.

    Node types:  project | branch | note | decision | evidence | output
    Edge types:  contains | related_to | decided_by | derived_from | supported_by

    Inferred edges are tagged with inferred=True and rendered as dashed lines.
    Canonical vs non-canonical distinction is preserved on every node.
    """
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    p = site_data["project"]
    project_id = f"project/{p['slug']}"

    # Project root
    nodes.append({
        "id": project_id,
        "label": p["name"],
        "type": "project",
        "canonical": True,
        "summary": f"{p['profile']} project",
        "path": None,
    })

    # Branches and their leaves
    for branch in site_data.get("branches", []):
        bid = f"branch/{branch['path']}"
        nodes.append({
            "id": bid,
            "label": branch["title"],
            "type": "branch",
            "canonical": True,
            "summary": (branch.get("summary") or "")[:120],
            "path": branch["path"],
        })
        edges.append({
            "source": project_id,
            "target": bid,
            "type": "contains",
            "inferred": False,
        })

        for leaf in branch.get("leaves", []):
            nid = f"note/{leaf['path']}"
            nodes.append({
                "id": nid,
                "label": leaf["title"],
                "type": "note",
                "canonical": True,
                "summary": (leaf.get("summary") or "")[:100],
                "path": leaf["path"],
            })
            edges.append({
                "source": bid,
                "target": nid,
                "type": "contains",
                "inferred": False,
            })

    # Decisions
    for decision in site_data.get("decisions", []):
        did = f"decision/{decision['path']}"
        nodes.append({
            "id": did,
            "label": decision["title"],
            "type": "decision",
            "canonical": True,
            "summary": (decision.get("summary") or "")[:100],
            "path": decision["path"],
        })
        # Structural edge from project
        edges.append({
            "source": project_id,
            "target": did,
            "type": "decided_by",
            "inferred": False,
        })

    # Evidence — skip README stubs and capture logs
    for ev in site_data.get("evidence", []):
        title = ev.get("title", "")
        path = ev.get("path", "")
        if title.lower() in ("readme", "") or path.endswith("README.md"):
            continue
        eid = f"evidence/{path}"
        nodes.append({
            "id": eid,
            "label": title,
            "type": "evidence",
            "canonical": False,
            "summary": (ev.get("summary") or "")[:100],
            "path": path,
        })
        edges.append({
            "source": project_id,
            "target": eid,
            "type": "supported_by",
            "inferred": True,
        })

    # Outputs — skip site/ self-references
    for out in site_data.get("outputs", []):
        path = out.get("path", "")
        if "site/" in path or path.startswith("Outputs/site") or path.startswith("Views/site"):
            continue
        oid = f"output/{path}"
        nodes.append({
            "id": oid,
            "label": out.get("title", path),
            "type": "output",
            "canonical": False,
            "summary": (out.get("summary") or "")[:100],
            "path": path,
        })
        edges.append({
            "source": project_id,
            "target": oid,
            "type": "derived_from",
            "inferred": True,
        })

    # Wikilink edges — resolve [[Target]] links between nodes
    # Build a case-insensitive label → node_id lookup
    label_to_id: dict[str, str] = {}
    for node in nodes:
        label_to_id[node["label"].lower()] = node["id"]
        if node.get("path"):
            # Also index by stem (filename without extension)
            stem = Path(node["path"]).stem.lower()
            if stem not in label_to_id:
                label_to_id[stem] = node["id"]

    # Collect node html by id so we can scan for wikilinks
    def _collect_html_sources() -> list[tuple[str, str]]:
        """Yield (node_id, html) for every node that has html content."""
        pairs: list[tuple[str, str]] = []
        for branch in site_data.get("branches", []):
            bid = f"branch/{branch['path']}"
            if branch.get("html"):
                pairs.append((bid, branch["html"]))
            for leaf in branch.get("leaves", []):
                nid = f"note/{leaf['path']}"
                if leaf.get("html"):
                    pairs.append((nid, leaf["html"]))
        for decision in site_data.get("decisions", []):
            did = f"decision/{decision['path']}"
            if decision.get("html"):
                pairs.append((did, decision["html"]))
        for ev in site_data.get("evidence", []):
            eid = f"evidence/{ev['path']}"
            if ev.get("html"):
                pairs.append((eid, ev["html"]))
        return pairs

    seen_edges: set[tuple[str, str]] = set()
    wikilink_re = re.compile(r'data-target="([^"]+)"')
    for source_id, html in _collect_html_sources():
        for m in wikilink_re.finditer(html):
            target_label = m.group(1).strip().lower()
            target_id = label_to_id.get(target_label)
            if target_id and target_id != source_id:
                key = (source_id, target_id)
                if key not in seen_edges:
                    seen_edges.add(key)
                    edges.append({
                        "source": source_id,
                        "target": target_id,
                        "type": "related_to",
                        "inferred": False,
                    })

    return {
        "schema": _SITE_SCHEMA_VERSION,
        "generated": site_data.get("generated", ""),
        "project_slug": p["slug"],
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "node_count": len(nodes),
            "edge_count": len(edges),
        },
    }


# --------------------------------------------------------------------------- #
# HTML template                                                                #
# --------------------------------------------------------------------------- #

_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>__PROJECT_NAME__ — Knowledge</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#090e17;--surface:#0f1623;--surface-2:#161e2e;--surface-3:#1d2840;
  --border:#243044;--border-2:#1a2438;
  --text:#e2eaf8;--text-2:#c5d4ed;--muted:#7a90b0;--muted-2:#536180;
  --accent:#60a5fa;--accent-2:#a78bfa;--accent-3:#34d399;--accent-4:#fb923c;
  --accent-muted:#1e3a5f;
  --mem-bg:#071830;--mem-fg:#93c5fd;--mem-border:#2563eb;
  --ev-bg:#160d2e;--ev-fg:#c4b5fd;--ev-border:#7c3aed;
  --out-bg:#1c1000;--out-fg:#fbbf24;--out-border:#b45309;
  --ok:#4ade80;--warn-bg:#2d1600;--warn-fg:#fbbf24;
  --radius:10px;--radius-sm:6px;
  --glow-blue:0 0 20px rgba(96,165,250,.15);
  --glow-purple:0 0 20px rgba(167,139,250,.12);
}
html,body{height:100%;overflow:hidden}
body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;font-size:14px;line-height:1.6}

/* ---- LAYOUT ---- */
#root{display:grid;grid-template-columns:268px 1fr;grid-template-rows:100vh;overflow:hidden}

/* ---- SIDEBAR ---- */
#sidebar{background:var(--surface);border-right:1px solid var(--border);display:flex;flex-direction:column;overflow:hidden}
.sidebar-header{padding:16px 14px 13px;border-bottom:1px solid var(--border);flex-shrink:0;background:linear-gradient(160deg,#0f1a2e 0%,#0c1524 100%)}
.sidebar-logo{display:flex;align-items:center;gap:7px;color:var(--muted);font-size:11px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;margin-bottom:10px}
.sidebar-logo-mark{width:20px;height:20px;background:linear-gradient(135deg,var(--accent),var(--accent-2));border-radius:5px;display:inline-flex;align-items:center;justify-content:center;color:#fff;font-weight:900;font-size:10px;flex-shrink:0;box-shadow:var(--glow-blue)}
.sidebar-project-name{font-size:15px;font-weight:700;color:var(--text);margin-bottom:6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;letter-spacing:-.2px}
.sidebar-meta{display:flex;gap:5px;flex-wrap:wrap;align-items:center}
#sidebar-tree{flex:1;overflow-y:auto;padding:8px 0}
.tree-group{margin-bottom:3px}
.tree-group-header{padding:8px 12px 5px;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);display:flex;align-items:center;gap:6px;user-select:none}
.tree-group-header .count{background:var(--surface-2);border-radius:9px;padding:0 6px;font-size:9px;margin-left:auto;color:var(--muted-2)}
.tree-item{padding:5px 12px 5px 18px;cursor:pointer;color:var(--muted);font-size:13px;display:flex;align-items:center;gap:7px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;transition:background .12s,color .12s;border-radius:6px;margin:1px 6px}
.tree-item:hover{background:var(--surface-2);color:var(--text-2)}
.tree-item.active{background:linear-gradient(90deg,var(--mem-bg),transparent);color:var(--accent);border-left:2px solid var(--accent)}
.tree-item.leaf{padding-left:28px;font-size:12px}
.tree-item.branch{font-weight:500}
.tree-item-icon{font-size:13px;flex-shrink:0}
.tree-item-label{overflow:hidden;text-overflow:ellipsis;flex:1}
.tree-sep{height:1px;background:var(--border-2);margin:7px 12px}
.sidebar-footer{padding:9px 12px;border-top:1px solid var(--border);flex-shrink:0;font-size:10px;color:var(--muted-2);line-height:1.6}

/* ---- MAIN ---- */
#main{display:flex;flex-direction:column;overflow:hidden;position:relative;height:100%}

/* ---- TOPBAR ---- */
#topbar{height:48px;background:var(--surface);border-bottom:1px solid var(--border);display:flex;align-items:center;padding:0 20px;gap:14px;flex-shrink:0;z-index:6;position:relative}
#breadcrumb{flex:1;font-size:13px;color:var(--muted);display:flex;align-items:center;gap:5px;overflow:hidden}
#breadcrumb a{color:var(--accent);text-decoration:none;flex-shrink:0}
#breadcrumb a:hover{text-decoration:underline}
.bc-sep{color:var(--muted-2);flex-shrink:0}
.bc-current{color:var(--text-2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#topbar-tabs{display:flex;gap:3px;flex-shrink:0}
.tab-btn{background:none;border:1px solid transparent;border-radius:var(--radius-sm);color:var(--muted);cursor:pointer;font-size:12px;padding:5px 12px;transition:all .15s;font-weight:500}
.tab-btn:hover{color:var(--text);background:var(--surface-2)}
.tab-btn.active{color:var(--accent);border-color:var(--mem-border);background:var(--mem-bg);box-shadow:var(--glow-blue)}

/* ---- CONTENT ---- */
#view-wrap{flex:1;position:relative;overflow:hidden}
#content{position:absolute;top:0;left:0;right:0;bottom:0;overflow-y:auto;padding:0}
.view-wrap{max-width:900px;margin:0 auto;padding:28px 32px}

/* ---- OVERVIEW ---- */
.ov-header{padding-bottom:22px;margin-bottom:28px;border-bottom:1px solid var(--border)}
.ov-title{font-size:28px;font-weight:800;letter-spacing:-.6px;margin-bottom:10px;background:linear-gradient(90deg,var(--text) 60%,var(--accent));-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
.ov-meta{display:flex;gap:10px;flex-wrap:wrap;align-items:center;font-size:12px;color:var(--muted)}
.ov-meta-item{display:flex;align-items:center;gap:4px}
.status-ok{color:var(--ok)}
.status-pending{color:var(--warn-fg)}
.sep-dot{color:var(--border)}

.warnings-box{background:var(--warn-bg);border:1px solid var(--warn-fg);border-radius:var(--radius);padding:13px 16px;margin-bottom:24px}
.warnings-box h3{color:var(--warn-fg);font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px}
.warn-item{color:var(--warn-fg);font-size:13px;margin-bottom:4px;display:flex;gap:8px}
.warn-item::before{content:"⚠";flex-shrink:0}

.section{margin-bottom:36px}
.section-heading{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);margin-bottom:14px;display:flex;align-items:center;gap:9px}
.section-heading .sh-icon{font-size:14px;opacity:.9}
.section-heading::after{content:"";flex:1;height:1px;background:linear-gradient(90deg,var(--border),transparent)}

.branch-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:10px}
.branch-card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:12px 14px;cursor:pointer;transition:border-color .15s,background .15s,box-shadow .15s;display:flex;flex-direction:column}
.branch-card:hover{border-color:var(--accent);background:var(--surface-2);box-shadow:var(--glow-blue)}
.branch-card-top{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:5px;gap:6px}
.branch-card-title{font-weight:600;font-size:13px;color:var(--text);flex:1}
.branch-card-purpose{font-size:12px;color:var(--muted);line-height:1.5;margin-bottom:8px;flex:1}
.branch-card-foot{font-size:10.5px;color:var(--muted-2);display:flex;gap:8px;align-items:center;margin-top:auto}
.bc-changes{color:var(--accent-3);font-weight:600}
.bc-updated{color:var(--muted-2);margin-left:auto}

.changes-list{display:flex;flex-direction:column;gap:0}
.change-row{display:grid;grid-template-columns:90px auto 1fr;gap:10px;align-items:baseline;padding:7px 0;border-bottom:1px solid var(--border-2);font-size:13px}
.change-date{color:var(--muted-2);font-size:11px;font-variant-numeric:tabular-nums;white-space:nowrap}
.change-branch-tag{color:var(--mem-fg);font-size:10px;font-weight:600;background:var(--mem-bg);border-radius:9px;padding:1px 8px;white-space:nowrap;border:1px solid var(--mem-border)}
.change-text{color:var(--text-2)}

.decision-list{display:flex;flex-direction:column;gap:7px}
.decision-item{background:var(--surface);border:1px solid var(--border);border-left:3px solid var(--accent-2);border-radius:var(--radius-sm);padding:10px 14px;cursor:pointer;transition:all .15s}
.decision-item:hover{border-color:var(--accent-2);background:var(--surface-2);box-shadow:var(--glow-purple)}
.decision-item-title{font-size:13px;font-weight:600;color:var(--accent-2);margin-bottom:4px}
.decision-item-what{font-size:12px;color:var(--muted)}
.decision-item-date{font-size:11px;color:var(--muted-2);margin-top:5px}

.question-list{list-style:none;display:flex;flex-direction:column;gap:6px}
.question-item{font-size:13px;display:flex;gap:9px;align-items:baseline}
.q-branch{font-size:10px;color:var(--muted);background:var(--surface);border-radius:9px;padding:2px 8px;white-space:nowrap;flex-shrink:0;border:1px solid var(--border)}
.q-text{color:var(--text-2)}

/* ---- NOTE VIEW ---- */
.note-wrap{max-width:800px;margin:0 auto;padding:28px 32px}
.note-breadcrumb{display:flex;align-items:center;gap:5px;font-size:12px;color:var(--muted);margin-bottom:18px;flex-wrap:wrap}
.note-breadcrumb a{color:var(--accent);text-decoration:none}
.note-breadcrumb a:hover{text-decoration:underline}
.note-header{margin-bottom:22px;padding-bottom:18px;border-bottom:1px solid var(--border)}
.note-badges{display:flex;gap:6px;align-items:center;margin-bottom:10px;flex-wrap:wrap}
.note-type-label{font-size:11px;color:var(--muted)}
.note-title{font-size:24px;font-weight:700;letter-spacing:-.4px;margin-bottom:9px;color:var(--text)}
.note-meta{display:flex;gap:11px;font-size:12px;color:var(--muted);flex-wrap:wrap}
.note-canonical{color:var(--ok)}
.note-non-canonical{color:var(--ev-fg)}

.nc-warning{background:#1a0a00;border:1px solid var(--ev-border);border-radius:var(--radius-sm);padding:10px 14px;margin-bottom:18px;font-size:12px;color:var(--ev-fg)}

/* TOC */
.toc{background:var(--surface);border:1px solid var(--border);border-left:3px solid var(--accent);border-radius:var(--radius);padding:12px 16px;margin-bottom:24px;font-size:13px}
.toc-title{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);margin-bottom:8px}
.toc ul{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:3px}
.toc li a{color:var(--accent);text-decoration:none;opacity:.85;transition:opacity .12s}
.toc li a:hover{opacity:1;text-decoration:underline}

/* Note body markdown */
.note-body{color:var(--text-2);line-height:1.78}
.note-body h1,.note-body h2,.note-body h3,.note-body h4{position:relative}
.note-body h1{font-size:21px;font-weight:700;margin:26px 0 11px;color:var(--text)}
.note-body h2{font-size:17px;font-weight:600;margin:24px 0 9px;color:var(--text);padding-bottom:6px;border-bottom:1px solid var(--border)}
.note-body h3{font-size:15px;font-weight:600;margin:18px 0 7px;color:var(--text-2)}
.note-body h4{font-size:13px;font-weight:600;margin:14px 0 6px;color:var(--muted)}
.note-body .anchor{position:absolute;left:-18px;color:var(--muted-2);text-decoration:none;opacity:0;font-weight:400;font-size:.85em;transition:opacity .12s}
.note-body h1:hover .anchor,.note-body h2:hover .anchor,.note-body h3:hover .anchor,.note-body h4:hover .anchor{opacity:1}
.note-body p{margin:8px 0}
.note-body ul,.note-body ol{margin:8px 0 8px 22px}
.note-body li{margin:4px 0}
.note-body code{background:var(--surface-2);border:1px solid var(--border);border-radius:4px;padding:1px 6px;font-family:ui-monospace,"Cascadia Code","Fira Code",monospace;font-size:12px;color:var(--accent-3)}
.note-body pre{background:var(--surface);border:1px solid var(--border);border-top:2px solid var(--accent);border-radius:var(--radius);padding:15px 17px;overflow-x:auto;margin:14px 0}
.note-body pre code{background:none;border:none;padding:0;font-size:12.5px;color:var(--text-2)}
.note-body blockquote{border-left:3px solid var(--accent-2);padding:4px 0 4px 14px;color:var(--muted);margin:12px 0;background:rgba(167,139,250,.04);border-radius:0 var(--radius-sm) var(--radius-sm) 0}
.note-body a{color:var(--accent)}
.note-body a.wikilink{color:var(--accent-2);text-decoration:none;border-bottom:1px dashed var(--accent-2);cursor:pointer}
.note-body a.wikilink:hover{border-bottom-style:solid}
.note-body a.wikilink-missing{color:var(--muted);border-bottom:1px dashed var(--muted);cursor:default}
.note-body hr{border:none;border-top:1px solid var(--border);margin:20px 0}
.note-body .mermaid{background:var(--surface-2);border:1px solid var(--border);border-radius:var(--radius);padding:20px;margin:16px 0;overflow-x:auto;text-align:center}
.note-body .mermaid svg{max-width:100%;height:auto}
.note-body table{border-collapse:collapse;width:100%;margin:16px 0;font-size:13px}
.note-body th{background:linear-gradient(90deg,var(--mem-bg),var(--surface-2));padding:8px 13px;text-align:left;border:1px solid var(--border);font-weight:600;color:var(--mem-fg)}
.note-body td{padding:7px 13px;border:1px solid var(--border);color:var(--text-2)}
.note-body tr:nth-child(even) td{background:var(--surface)}
.note-body strong{color:var(--text);font-weight:600}
.note-body em{color:var(--text-2);font-style:italic}

.related-section{margin-top:34px;padding-top:20px;border-top:1px solid var(--border)}
.related-section h4{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:var(--muted-2);margin-bottom:11px}
.related-list{display:flex;flex-direction:column;gap:6px}
.related-item{display:flex;flex-direction:column;gap:3px;text-decoration:none;padding:10px 13px;background:var(--surface);border-radius:var(--radius-sm);border:1px solid var(--border);transition:all .15s}
.related-item:hover{border-color:var(--accent);box-shadow:var(--glow-blue)}
.related-item-title{color:var(--accent);font-size:13px;font-weight:500}
.related-item-summary{color:var(--muted);font-size:12px}

/* ---- EVIDENCE VIEW ---- */
.evidence-list{display:flex;flex-direction:column;gap:8px}
.ev-card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:13px 15px;cursor:pointer;transition:border-color .15s}
.ev-card:hover{border-color:var(--ev-border)}
.ev-card-top{display:flex;justify-content:space-between;align-items:flex-start;gap:8px;margin-bottom:5px}
.ev-card-title{font-weight:500;font-size:13px;color:var(--text);flex:1}
.ev-source{font-size:11px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%;margin-bottom:4px}
.ev-date{font-size:11px;color:var(--muted-2)}
.empty-state{text-align:center;color:var(--muted);padding:48px 20px;font-size:14px}

/* ---- BADGES ---- */
.badge{display:inline-flex;align-items:center;padding:2px 8px;border-radius:12px;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;flex-shrink:0}
.badge-Memory{background:var(--mem-bg);color:var(--mem-fg);border:1px solid var(--mem-border)}
.badge-Evidence{background:var(--ev-bg);color:var(--ev-fg);border:1px solid var(--ev-border)}
.badge-Outputs{background:var(--out-bg);color:var(--out-fg);border:1px solid var(--out-border)}
.badge-profile{background:var(--surface-2);color:var(--muted);border:1px solid var(--border);font-size:9px}
.badge-onboarding-ok{background:#0d2b0d;color:var(--ok);border:1px solid #1a4d1a;font-size:9px}
.badge-onboarding-pending{background:var(--warn-bg);color:var(--warn-fg);border:1px solid var(--warn-fg);font-size:9px}

/* ---- GRAPH VIEW ---- */
#graph-container{position:absolute;top:0;left:0;right:0;bottom:0;display:none;background:var(--bg);z-index:5;overflow:hidden}
#graph-container.visible{display:block}
#graph-canvas{position:absolute;top:0;left:0;width:100%;height:100%;display:block;cursor:grab}
#graph-canvas.gdrag{cursor:grabbing}

/* graph controls bar — single slim row */
#gc-bar{position:absolute;top:12px;left:12px;right:230px;display:flex;align-items:center;gap:6px;background:rgba(13,17,23,.88);border:1px solid var(--border);border-radius:20px;padding:5px 12px;z-index:10;backdrop-filter:blur(8px)}
#gc-search{background:transparent;border:none;border-right:1px solid var(--border);color:var(--text);font-size:12px;outline:none;padding:2px 10px 2px 2px;width:150px;transition:border-color .15s;margin-right:4px}
#gc-search::placeholder{color:var(--muted-2)}
#gc-search:focus{border-right-color:var(--accent)}
.gc-sep{color:var(--border);padding:0 1px;font-size:10px;user-select:none}
.gc-lbl{color:var(--muted-2);font-size:10px;font-weight:600;letter-spacing:.03em;flex-shrink:0}
.gf-btn{background:transparent;border:1px solid transparent;border-radius:10px;color:var(--muted);cursor:pointer;font-size:10px;font-weight:600;padding:2px 8px;transition:all .12s}
.gf-btn.active{background:rgba(56,139,253,.15);border-color:rgba(56,139,253,.4);color:#79c0ff}
.gf-btn:hover{color:var(--text)}
.gcf-btn{background:transparent;border:1px solid transparent;border-radius:10px;color:var(--muted);cursor:pointer;font-size:10px;padding:2px 8px;transition:all .12s}
.gcf-btn.active{background:rgba(88,166,255,.15);border-color:rgba(88,166,255,.4);color:var(--accent)}

/* graph legend — bottom strip */
#gc-legend{position:absolute;bottom:12px;left:12px;background:rgba(13,17,23,.8);border:1px solid var(--border-2);border-radius:14px;padding:5px 12px;display:flex;gap:12px;align-items:center;z-index:10;backdrop-filter:blur(4px)}
.gl-item{display:flex;align-items:center;gap:4px;font-size:10px;color:var(--muted);white-space:nowrap}
.gl-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0;border:1.5px solid transparent}
.gc-hint{color:var(--muted-2);font-size:10px;font-style:italic}

/* graph info panel */
#gc-info{position:absolute;top:10px;right:10px;width:210px;background:rgba(22,27,34,.97);border:1px solid var(--border);border-radius:var(--radius);padding:13px 15px;z-index:10;display:none;backdrop-filter:blur(6px)}
#gc-info.visible{display:block}
.gi-close{position:absolute;top:8px;right:10px;background:none;border:none;color:var(--muted);cursor:pointer;font-size:16px;line-height:1;padding:0}
.gi-close:hover{color:var(--text)}
.gi-type{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);margin-bottom:3px}
.gi-title{font-size:13px;font-weight:600;color:var(--text);margin-bottom:6px;word-break:break-word;padding-right:14px}
.gi-summary{font-size:11px;color:var(--muted);line-height:1.5;margin-bottom:7px}
.gi-cn{font-size:10px;margin-bottom:8px}
.gi-cn.ok{color:var(--ok)}
.gi-cn.nc{color:var(--ev-fg)}
.gi-open{background:var(--accent-muted);border:none;border-radius:var(--radius-sm);color:var(--text);cursor:pointer;display:block;font-size:12px;padding:5px;text-align:center;width:100%;transition:background .15s}
.gi-open:hover{background:var(--accent);color:#000}

/* graph controls / zoom */
#gc-zoom{position:absolute;bottom:10px;right:10px;display:flex;flex-direction:column;gap:4px;z-index:10}
.gcz-btn{background:var(--surface-2);border:1px solid var(--border);border-radius:var(--radius-sm);color:var(--muted);cursor:pointer;font-size:14px;line-height:1;padding:5px 8px;transition:all .15s;display:flex;align-items:center;justify-content:center}
.gcz-btn:hover{color:var(--text);border-color:var(--accent)}

/* graph empty state */
#gc-empty{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);text-align:center;color:var(--muted);font-size:14px;pointer-events:none}
</style>
<script type="module">
import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
mermaid.initialize({
  startOnLoad: false,
  theme: 'dark',
  themeVariables: {
    background: '#0f1623',
    primaryColor: '#1e3a5f',
    primaryTextColor: '#e2eaf8',
    primaryBorderColor: '#243044',
    lineColor: '#7a90b0',
    secondaryColor: '#160d2e',
    tertiaryColor: '#1d2840',
    edgeLabelBackground: '#0f1623',
    fontFamily: '-apple-system,system-ui,sans-serif',
    fontSize: '13px'
  }
});
window._mermaid = mermaid;
</script>
</head>
<body>
<div id="root">
  <aside id="sidebar">
    <div class="sidebar-header">
      <div class="sidebar-logo"><span class="sidebar-logo-mark">BR</span>bedrock</div>
      <div class="sidebar-project-name">__PROJECT_NAME__</div>
      <div class="sidebar-meta" id="sidebar-meta"></div>
    </div>
    <div id="sidebar-tree"></div>
    <div class="sidebar-footer">
      Generated __GENERATED__<br>
      Non-canonical derived artifact — vault is the source of truth
    </div>
  </aside>
  <div id="main">
    <div id="topbar">
      <div id="breadcrumb"><span class="bc-current">Overview</span></div>
      <div id="topbar-tabs">
        <button class="tab-btn active" data-view="overview" onclick="nav('overview')">Overview</button>
        <button class="tab-btn" data-view="evidence" onclick="nav('evidence')">Evidence</button>
        <button class="tab-btn" data-view="graph" onclick="nav('graph')">Graph</button>
      </div>
    </div>
    <div id="view-wrap">
    <div id="content"></div>
    <!-- Graph container: same layer as #content, shown/hidden by toggling display -->
    <div id="graph-container">
      <canvas id="graph-canvas"></canvas>
      <div id="gc-bar">
        <input id="gc-search" type="text" placeholder="Search..." />
        <span class="gc-sep">|</span>
        <span class="gc-lbl">Type</span>
        <button class="gf-btn active" data-type="branch">Branch</button>
        <button class="gf-btn active" data-type="note">Note</button>
        <button class="gf-btn active" data-type="decision">Decision</button>
        <button class="gf-btn active" data-type="evidence">Evidence</button>
        <button class="gf-btn active" data-type="output">Output</button>
        <span class="gc-sep">|</span>
        <button class="gcf-btn active" data-val="all">All</button>
        <button class="gcf-btn" data-val="canonical">Canonical only</button>
      </div>
      <div id="gc-legend">
        <span class="gl-item"><span class="gl-dot" style="background:#0a2447;border-color:#58a6ff"></span>Project</span>
        <span class="gl-item"><span class="gl-dot" style="background:#0d2744;border-color:#388bfd"></span>Branch</span>
        <span class="gl-item"><span class="gl-dot" style="background:#0d1b2e;border-color:#1f6feb"></span>Note</span>
        <span class="gl-item"><span class="gl-dot" style="background:#0b2d0b;border-color:#3fb950"></span>Decision</span>
        <span class="gl-item"><span class="gl-dot" style="background:#1b0042;border-color:#8957e5"></span>Evidence</span>
        <span class="gl-item"><span class="gl-dot" style="background:#2a1500;border-color:#9e6a03"></span>Output</span>
        <span class="gl-item"><span class="gl-dot" style="background:transparent;border-color:#6e40c9"></span>Non-canonical</span>
        <span class="gc-hint">Scroll=zoom · Drag=pan · Click=select</span>
      </div>
      <div id="gc-info">
        <button class="gi-close" onclick="closeInfoPanel()" title="Close">✕</button>
        <div id="gc-info-body"></div>
      </div>
      <div id="gc-zoom">
        <button class="gcz-btn" onclick="graphZoomIn()" title="Zoom in">+</button>
        <button class="gcz-btn" onclick="graphZoomOut()" title="Zoom out">−</button>
        <button class="gcz-btn" onclick="resetGraphView()" title="Reset view" style="font-size:10px">⊙</button>
      </div>
      <div id="gc-empty" style="display:none">No nodes to display.<br>Adjust filters or run bedrock sync first.</div>
    </div>
    </div><!-- /view-wrap -->
  </div><!-- /main -->
</div><!-- /root -->

<script>
const DATA = __DATA_JSON__;
const GRAPH_DATA = __GRAPH_JSON__;

let _view = 'overview';
let _notePath = null;
const memoryRootPath = (DATA.project && DATA.project.memory_root_path) || 'Memory/PROJECT.md';

// ---- Helpers ----
function esc(s){
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function badge(folder){
  return `<span class="badge badge-${esc(folder)}">${esc(folder)}</span>`;
}
function encP(s){ return encodeURIComponent(s); }

// ---- Navigation ----
function nav(view, arg){
  if(view==='overview') location.hash='overview';
  else if(view==='note') location.hash='note/'+encP(arg);
  else if(view==='evidence') location.hash='evidence';
  else if(view==='graph') location.hash='graph';
}

function _hideGraph(){
  const gc = document.getElementById('graph-container');
  if(gc) gc.classList.remove('visible');
  if(_simFrame){ cancelAnimationFrame(_simFrame); _simFrame=null; }
  _simRunning = false;
}

function handleHash(){
  const h = location.hash.slice(1);
  if(!h||h==='overview') showOverview();
  else if(h.startsWith('note/')) showNote(decodeURIComponent(h.slice(5)));
  else if(h==='evidence') showEvidence();
  else if(h==='graph') showGraph();
  else showOverview();
}

// ---- Sidebar ----
function buildSidebar(){
  const meta = document.getElementById('sidebar-meta');
  const profile = DATA.project.profile||'unknown';
  const onb = DATA.project.onboarding||'unknown';
  const onbCls = onb==='complete'?'badge-onboarding-ok':'badge-onboarding-pending';
  meta.innerHTML = `<span class="badge badge-profile">${esc(profile)}</span><span class="badge ${onbCls}">${esc(onb)}</span>`;

  const tree = document.getElementById('sidebar-tree');
  let h = '';

  // Memory group
  h += '<div class="tree-group">';
  h += `<div class="tree-group-header"><span>📘</span> Memory</div>`;
  for(const b of DATA.branches){
    if(b.path===memoryRootPath) continue;
    h += `<div class="tree-item branch" data-path="${esc(b.path)}" onclick="nav('note','${esc(b.path)}')" title="${esc(b.path)}">`;
    h += `<span class="tree-item-icon">◆</span><span class="tree-item-label">${esc(b.title)}</span></div>`;
    for(const lf of (b.leaves||[])){
      h += `<div class="tree-item leaf" data-path="${esc(lf.path)}" onclick="nav('note','${esc(lf.path)}')" title="${esc(lf.path)}">`;
      h += `<span class="tree-item-icon">·</span><span class="tree-item-label">${esc(lf.title)}</span></div>`;
    }
  }

  // Decisions
  if(DATA.decisions&&DATA.decisions.length>0){
    h += '<div class="tree-sep"></div>';
    h += '<div class="tree-group-header"><span>⚡</span> Decisions</div>';
    for(const d of DATA.decisions){
      h += `<div class="tree-item leaf" data-path="${esc(d.path)}" onclick="nav('note','${esc(d.path)}')" title="${esc(d.path)}">`;
      h += `<span class="tree-item-icon">△</span><span class="tree-item-label">${esc(d.title)}</span></div>`;
    }
  }
  h += '</div>';

  // Evidence group
  if(DATA.evidence&&DATA.evidence.length>0){
    h += '<div class="tree-sep"></div>';
    h += '<div class="tree-group">';
    h += `<div class="tree-group-header"><span>📎</span> Evidence<span class="count">${DATA.evidence.length}</span></div>`;
    for(const e of DATA.evidence){
      h += `<div class="tree-item leaf" data-path="${esc(e.path)}" onclick="nav('note','${esc(e.path)}')" title="${esc(e.path)}">`;
      h += `<span class="tree-item-icon">·</span><span class="tree-item-label">${esc(e.title)}</span></div>`;
    }
    h += '</div>';
  }

  tree.innerHTML = h;
}

function setSidebarActive(path){
  document.querySelectorAll('#sidebar-tree .tree-item').forEach(el=>{
    el.classList.toggle('active', el.dataset.path===path);
  });
}

// ---- Topbar ----
function setTopbar(view, note){
  const bc = document.getElementById('breadcrumb');
  document.querySelectorAll('.tab-btn').forEach(b=>{
    b.classList.toggle('active', b.dataset.view===view);
  });
  if(view==='overview'){
    bc.innerHTML='<span class="bc-current">Overview</span>';
  } else if(view==='evidence'){
    bc.innerHTML='<span class="bc-current">Evidence</span>';
  } else if(view==='graph'){
    bc.innerHTML='<span class="bc-current">Graph</span>';
  } else if(view==='note'&&note){
    const folderBadge = badge(note.folder);
    bc.innerHTML = `<a href="#overview" onclick="event.preventDefault();nav('overview')">Overview</a>`
      +`<span class="bc-sep">›</span>${folderBadge}`
      +`<span class="bc-sep">›</span><span class="bc-current">${esc(note.title)}</span>`;
  }
}

// ---- Overview ----
function showOverview(){
  _hideGraph();
  _view='overview'; _notePath=null;
  const content = document.getElementById('content');
  let h = '<div class="view-wrap">';

  const p = DATA.project;
  const onb = p.onboarding||'unknown';
  const onbOk = onb==='complete';
  h += `<div class="ov-header"><div class="ov-title">${esc(p.name)}</div>`;
  h += `<div class="ov-meta">`;
  h += `<span class="ov-meta-item">slug: <code>${esc(p.slug)}</code></span>`;
  h += `<span class="sep-dot">·</span>`;
  if(p.profile&&p.profile!=='unknown') {
    h += `<span class="ov-meta-item">profile: ${esc(p.profile)}</span>`;
    h += `<span class="sep-dot">·</span>`;
  }
  const onbColor = onbOk?'status-ok':'status-pending';
  h += `<span class="ov-meta-item ${onbColor}">onboarding: ${esc(onb)}</span>`;
  if(DATA.stats){
    h += `<span class="sep-dot">·</span><span class="ov-meta-item">${DATA.stats.branch_count} branches · ${DATA.stats.decision_count} decisions · ${DATA.stats.evidence_count} evidence</span>`;
  }
  h += `</div></div>`;

  if(DATA.warnings&&DATA.warnings.length>0){
    h += `<div class="warnings-box"><h3>Warnings</h3>`;
    for(const w of DATA.warnings) h += `<div class="warn-item">${esc(w)}</div>`;
    h += `</div>`;
  }

  const mainBranches = DATA.branches.filter(b=>b.path!==memoryRootPath);
  if(mainBranches.length>0){
    h += `<div class="section"><div class="section-heading"><span class="sh-icon">📘</span>Knowledge Branches</div>`;
    h += `<div class="branch-grid">`;
    for(const b of mainBranches){
      const summary = b.summary||b.purpose||'';
      const changesN = (b.recent_changes||[]).length;
      h += `<div class="branch-card" onclick="nav('note','${esc(b.path)}')">`;
      h += `<div class="branch-card-top"><span class="branch-card-title">${esc(b.title)}</span>${badge('Memory')}</div>`;
      h += `<div class="branch-card-purpose">${esc(summary.substring(0,110))}${summary.length>110?'…':''}</div>`;
      h += `<div class="branch-card-foot">`;
      if(changesN>0) h += `<span class="bc-changes">${changesN} change${changesN>1?'s':''}</span>`;
      if(b.updated) h += `<span class="bc-updated">updated ${esc(b.updated)}</span>`;
      h += `</div>`;
      h += `</div>`;
    }
    h += `</div></div>`;
  }

  if(DATA.recent_changes_global&&DATA.recent_changes_global.length>0){
    h += `<div class="section"><div class="section-heading"><span class="sh-icon">🕐</span>Recent Changes</div><div class="changes-list">`;
    for(const c of DATA.recent_changes_global){
      h += `<div class="change-row">`;
      h += `<span class="change-date">${esc(c.date)}</span>`;
      h += `<span class="change-branch-tag">${esc(c.branch)}</span>`;
      h += `<span class="change-text">${esc(c.text)}</span>`;
      h += `</div>`;
    }
    h += `</div></div>`;
  }

  if(DATA.decisions&&DATA.decisions.length>0){
    const shown = DATA.decisions.slice(0,8);
    h += `<div class="section"><div class="section-heading"><span class="sh-icon">⚡</span>Key Decisions</div><div class="decision-list">`;
    for(const d of shown){
      h += `<div class="decision-item" onclick="nav('note','${esc(d.path)}')">`;
      h += `<div class="decision-item-title">${esc(d.title)}</div>`;
      if(d.what) h += `<div class="decision-item-what">${esc(d.what.substring(0,160))}${d.what.length>160?'...':''}</div>`;
      if(d.date) h += `<div class="decision-item-date">${esc(d.date)}</div>`;
      h += `</div>`;
    }
    h += `</div></div>`;
  }

  const allQ = DATA.branches.flatMap(b=>(b.open_questions||[]).map(q=>({q,branch:b.title})));
  if(allQ.length>0){
    h += `<div class="section"><div class="section-heading"><span class="sh-icon">❓</span>Open Questions</div><ul class="question-list">`;
    for(const {q,branch} of allQ){
      h += `<li class="question-item"><span class="q-branch">${esc(branch)}</span><span class="q-text">${esc(q)}</span></li>`;
    }
    h += `</ul></div>`;
  }

  h += `</div>`;
  content.innerHTML = h;
  setTopbar('overview');
  setSidebarActive(null);
}

// ---- Note view ----
function findNote(path){
  for(const b of DATA.branches){
    if(b.path===path) return b;
    for(const lf of (b.leaves||[])){if(lf.path===path) return lf;}
  }
  for(const d of (DATA.decisions||[])){if(d.path===path) return d;}
  for(const e of (DATA.evidence||[])){if(e.path===path) return e;}
  return null;
}

function _allNotes(){
  const all=[];
  for(const b of DATA.branches){ all.push(b); for(const lf of (b.leaves||[])) all.push(lf); }
  for(const d of (DATA.decisions||[])) all.push(d);
  for(const e of (DATA.evidence||[])) all.push(e);
  return all;
}

function findNoteBySlug(target){
  const slug=target.toLowerCase().trim();
  return _allNotes().find(n=>{
    const stem=(n.path||'').split('/').pop().replace(/\.md$/i,'').toLowerCase();
    return stem===slug || (n.title||'').toLowerCase()===slug;
  })||null;
}

function resolveWikilinks(container){
  container.querySelectorAll('a.wikilink').forEach(el=>{
    const target=el.dataset.target||'';
    const note=findNoteBySlug(target);
    if(note){
      el.href='#note/'+encP(note.path);
      el.onclick=(e)=>{e.preventDefault();nav('note',note.path);};
    } else {
      el.classList.add('wikilink-missing');
      el.title='Note not found: '+target;
    }
  });
}

function renderMermaid(container){
  const els = Array.from(container.querySelectorAll('.mermaid')).filter(el=>!el.getAttribute('data-processed'));
  if(!els.length) return;
  if(window._mermaid){
    window._mermaid.run({nodes: els});
  } else {
    let tries = 0;
    const retry = () => {
      const live = els.filter(el=>document.body.contains(el)&&!el.getAttribute('data-processed'));
      if(!live.length) return;
      if(window._mermaid){ window._mermaid.run({nodes: live}); }
      else if(++tries < 20){ setTimeout(retry, 150); }
    };
    setTimeout(retry, 150);
  }
}

function showNote(path){
  _hideGraph();
  _view='note'; _notePath=path;
  const note = findNote(path);
  const content = document.getElementById('content');
  if(!note){
    content.innerHTML=`<div class="note-wrap"><div class="empty-state">Note not found: ${esc(path)}</div></div>`;
    return;
  }
  let h = `<div class="note-wrap">`;

  h += `<div class="note-breadcrumb">`;
  h += `<a href="#overview" onclick="event.preventDefault();nav('overview')">Overview</a>`;
  h += `<span class="bc-sep">›</span>${badge(note.folder)}`;
  h += `<span class="bc-sep">›</span><span>${esc(note.title)}</span>`;
  h += `</div>`;

  h += `<div class="note-header">`;
  h += `<div class="note-badges">${badge(note.folder)}`;
  if(note.note_type&&note.note_type!=='unknown') h += `<span class="note-type-label">${esc(note.note_type)}</span>`;
  h += `</div>`;
  h += `<div class="note-title">${esc(note.title)}</div>`;
  h += `<div class="note-meta">`;
  if(note.area) h += `<span>area: ${esc(note.area)}</span>`;
  if(note.updated) h += `<span>updated: ${esc(note.updated)}</span>`;
  const cnCls = note.canonical?'note-canonical':'note-non-canonical';
  h += `<span class="${cnCls}">${note.canonical?'canonical':'non-canonical'}</span>`;
  h += `</div></div>`;

  if(!note.canonical){
    h += `<div class="nc-warning">This note is in <strong>${esc(note.folder)}</strong> and is not canonical memory. Do not treat it as source of truth.</div>`;
  }

  h += `<div class="note-body">${note.html||''}</div>`;

  if(note.leaves&&note.leaves.length>0){
    h += `<div class="related-section"><h4>Branch Notes</h4><div class="related-list">`;
    for(const lf of note.leaves){
      h += `<a class="related-item" href="#note/${encP(lf.path)}" onclick="event.preventDefault();nav('note','${esc(lf.path)}')">`;
      h += `<span class="related-item-title">${esc(lf.title)}</span>`;
      if(lf.summary) h += `<span class="related-item-summary">${esc(lf.summary.substring(0,100))}</span>`;
      h += `</a>`;
    }
    h += `</div></div>`;
  }

  h += `</div>`;
  content.innerHTML = h;
  resolveWikilinks(content);
  renderMermaid(content);
  setTopbar('note', note);
  setSidebarActive(path);
  document.getElementById('content').scrollTop=0;
}

// ---- Evidence view ----
function showEvidence(){
  _hideGraph();
  _view='evidence'; _notePath=null;
  const content = document.getElementById('content');
  let h = `<div class="view-wrap">`;
  h += `<div class="ov-header"><div class="ov-title">Evidence</div>`;
  h += `<div class="ov-meta"><span>Imported and extracted material — non-canonical. Verify before using as source of truth.</span></div></div>`;

  if(!DATA.evidence||DATA.evidence.length===0){
    h += `<div class="empty-state">No evidence items in this vault.</div>`;
  } else {
    h += `<div class="evidence-list">`;
    for(const e of DATA.evidence){
      h += `<div class="ev-card" onclick="nav('note','${esc(e.path)}')">`;
      h += `<div class="ev-card-top"><span class="ev-card-title">${esc(e.title)}</span>${badge('Evidence')}</div>`;
      if(e.source) h += `<div class="ev-source">${esc(e.source)}</div>`;
      if(e.imported) h += `<div class="ev-date">Imported: ${esc(e.imported.split('T')[0])}</div>`;
      if(e.summary&&!e.source) h += `<div class="ev-date">${esc(e.summary.substring(0,120))}</div>`;
      h += `</div>`;
    }
    h += `</div>`;
  }
  h += `</div>`;
  content.innerHTML = h;
  setTopbar('evidence');
  setSidebarActive(null);
}

// =========================================================================
// GRAPH VIEW — self-contained force-directed graph (no external deps)
// =========================================================================

// Node visual constants
const GC = {
  project:  { fill:'#0a2447', stroke:'#58a6ff', label:'#79c0ff' },
  branch:   { fill:'#0d2744', stroke:'#388bfd', label:'#79c0ff' },
  note:     { fill:'#0d1b2e', stroke:'#1f6feb', label:'#8b949e' },
  decision: { fill:'#0b2d0b', stroke:'#3fb950', label:'#56d364' },
  evidence: { fill:'#1b0042', stroke:'#8957e5', label:'#d2a8ff' },
  output:   { fill:'#2a1500', stroke:'#9e6a03', label:'#e3b341' },
};
const GR = { project:22, branch:16, note:10, decision:13, evidence:9, output:9 };

// Simulation constants
const SIM_REPULSION = 18000;
const SIM_SPRING = 0.04;
const SIM_REST = 220;
const SIM_GRAVITY = 0.008;
const SIM_DAMPING = 0.82;

// Graph state
let _gNodes = [], _gEdges = [];
let _gZoom = 0.85, _gPanX = 0, _gPanY = 0;
let _gHovered = null, _gSelected = null;
let _gSearchQ = '';
let _gFilters = { types: new Set(['project','branch','note','decision','evidence','output']), canonical:'all' };
let _gCanvas = null, _gCtx = null;
let _gDragging = false, _gDragStart = null, _gNodeDrag = null;
let _simAlpha = 1, _simTick = 0, _simRunning = false, _simFrame = null;
let _graphInited = false;

function showGraph(){
  _view='graph'; _notePath=null;
  const gc = document.getElementById('graph-container');
  if(!gc) return;
  gc.classList.add('visible');
  setTopbar('graph');
  setSidebarActive(null);
  // Defer canvas work one frame so the browser can compute layout
  // after display:none → display:block (clientWidth/Height need reflow)
  requestAnimationFrame(()=>{
    if(!_graphInited){
      _graphInited = true;
      _initGraph();
    } else {
      // Restore canvas size (it collapses to 0 while display:none) then
      // just redraw at the stored node positions — no simulation restart.
      _resizeCanvasOnly();
      _renderGraph();
    }
  });
}

function _initGraph(){
  _gCanvas = document.getElementById('graph-canvas');
  if(!_gCanvas) return;
  _gCtx = _gCanvas.getContext('2d');

  const nodeMap = {};
  _gNodes = (GRAPH_DATA.nodes||[]).map(n=>{
    const nd = Object.assign({},n,{
      x:0, y:0, vx:0, vy:0, fx:0, fy:0,
      radius: GR[n.type]||10, visible:true
    });
    nodeMap[n.id] = nd;
    return nd;
  });
  _gEdges = (GRAPH_DATA.edges||[]).map(e=>({
    ...e, src:nodeMap[e.source], tgt:nodeMap[e.target]
  })).filter(e=>e.src&&e.tgt);

  _computeLayout();

  const cnt = _gCanvas.parentElement;
  _gPanX = cnt.clientWidth/2;
  _gPanY = cnt.clientHeight/2;

  _resizeGraph();
  window.addEventListener('resize', ()=>{ if(_view==='graph') _resizeGraph(); });

  _gCanvas.addEventListener('mousedown', _onGDown);
  _gCanvas.addEventListener('mousemove', _onGMove);
  _gCanvas.addEventListener('mouseup', _onGUp);
  _gCanvas.addEventListener('mouseleave', ()=>{ _gHovered=null; _renderGraph(); });
  _gCanvas.addEventListener('click', _onGClick);
  _gCanvas.addEventListener('wheel', _onGWheel, {passive:false});

  document.querySelectorAll('.gf-btn').forEach(b=>{
    b.addEventListener('click',()=>_toggleType(b.dataset.type));
  });
  document.querySelectorAll('.gcf-btn').forEach(b=>{
    b.addEventListener('click',()=>_setCanonicalFilter(b.dataset.val));
  });
  const si = document.getElementById('gc-search');
  if(si) si.addEventListener('input',e=>{
    _gSearchQ = e.target.value.toLowerCase().trim();
    _applyFilters();
  });

  _startSim();
}

function _computeLayout(){
  const proj = _gNodes.find(n=>n.type==='project');
  const branches = _gNodes.filter(n=>n.type==='branch');
  const decisions = _gNodes.filter(n=>n.type==='decision');
  const evidence = _gNodes.filter(n=>n.type==='evidence');
  const outputs = _gNodes.filter(n=>n.type==='output');

  if(proj){ proj.x=0; proj.y=0; }

  // Keep branch ring compact — cap radius so nodes stay on-screen
  const BR = Math.min(220, Math.max(120, branches.length*28));
  branches.forEach((b,i)=>{
    const a = (i/Math.max(1,branches.length))*2*Math.PI - Math.PI/2;
    b.x = Math.cos(a)*BR; b.y = Math.sin(a)*BR;
    const leaves = _gNodes.filter(n=>n.type==='note' &&
      _gEdges.some(e=>e.src===b&&e.tgt===n));
    leaves.forEach((lf,li)=>{
      const la = a + (li - leaves.length/2 + 0.5)*0.5;
      lf.x = b.x + Math.cos(la)*70;
      lf.y = b.y + Math.sin(la)*70;
    });
  });

  decisions.forEach((d,i)=>{
    const a = (i/Math.max(1,decisions.length))*Math.PI;
    d.x = Math.cos(a)*60; d.y = -BR - 90 + Math.sin(a)*40;
  });

  const evX = BR + 100;
  evidence.forEach((e,i)=>{
    e.x = evX + (i%2)*35;
    e.y = (i - evidence.length/2)*40;
  });

  const outX = -BR - 100;
  outputs.forEach((o,i)=>{
    o.x = outX - (i%2)*35;
    o.y = (i - outputs.length/2)*40;
  });
}

function _startSim(){
  _simAlpha = 1; _simTick = 0; _simRunning = true;
  if(_simFrame) cancelAnimationFrame(_simFrame);
  _simStep();
}

function _simStep(){
  if(!_simRunning) return;
  const vis = _gNodes.filter(n=>n.visible);
  if(vis.length===0){ _simRunning=false; return; }

  for(const n of vis){ n.fx=0; n.fy=0; }

  // Gravity
  for(const n of vis){
    n.fx -= SIM_GRAVITY*n.x*_simAlpha;
    n.fy -= SIM_GRAVITY*n.y*_simAlpha;
  }

  // Repulsion
  for(let i=0;i<vis.length;i++){
    const a=vis[i];
    for(let j=i+1;j<vis.length;j++){
      const b=vis[j];
      const dx=b.x-a.x, dy=b.y-a.y;
      const d2=dx*dx+dy*dy+0.01;
      const dist=Math.sqrt(d2);
      const f=SIM_REPULSION*_simAlpha/d2;
      const fx=f*dx/dist, fy=f*dy/dist;
      a.fx-=fx; a.fy-=fy; b.fx+=fx; b.fy+=fy;
    }
  }

  // Springs
  for(const e of _gEdges){
    if(!e.src||!e.tgt||!e.src.visible||!e.tgt.visible) continue;
    const dx=e.tgt.x-e.src.x, dy=e.tgt.y-e.src.y;
    const dist=Math.sqrt(dx*dx+dy*dy)||1;
    const disp=(dist-SIM_REST)*SIM_SPRING*_simAlpha;
    const fx=disp*dx/dist, fy=disp*dy/dist;
    e.src.fx+=fx; e.src.fy+=fy; e.tgt.fx-=fx; e.tgt.fy-=fy;
  }

  // Integrate
  for(const n of vis){
    n.vx=(n.vx+n.fx)*SIM_DAMPING;
    n.vy=(n.vy+n.fy)*SIM_DAMPING;
    n.x+=n.vx; n.y+=n.vy;
  }

  _simAlpha*=0.992;
  _simTick++;
  _renderGraph();

  if(_simAlpha>0.004&&_simTick<700){
    _simFrame = requestAnimationFrame(_simStep);
  } else {
    _simRunning=false;
    _renderGraph();
  }
}

function _resizeCanvasOnly(){
  // Resize the canvas backing buffer without touching pan/zoom or starting sim.
  // Used when returning to the graph tab after display:none collapsed it to 0.
  if(!_gCanvas) return;
  const cnt = _gCanvas.parentElement;
  const dpr = window.devicePixelRatio||1;
  const W = cnt.clientWidth, H = cnt.clientHeight;
  if(!W || !H){ requestAnimationFrame(()=>{ _resizeCanvasOnly(); _renderGraph(); }); return; }
  _gCanvas.width = W*dpr; _gCanvas.height = H*dpr;
  _gCanvas.style.width = W+'px'; _gCanvas.style.height = H+'px';
}

function _resizeGraph(){
  if(!_gCanvas) return;
  const cnt = _gCanvas.parentElement;
  const dpr = window.devicePixelRatio||1;
  let W = cnt.clientWidth, H = cnt.clientHeight;
  // If dimensions are zero the browser hasn't done layout yet — retry next frame
  if(!W || !H){
    requestAnimationFrame(_resizeGraph);
    return;
  }
  _gCanvas.width = W*dpr; _gCanvas.height = H*dpr;
  _gCanvas.style.width = W+'px'; _gCanvas.style.height = H+'px';
  if(_simTick===0){ _gPanX=W/2; _gPanY=H/2; }
  _renderGraph();
}

function _W(){ return _gCanvas?_gCanvas.width/(window.devicePixelRatio||1):0; }
function _H(){ return _gCanvas?_gCanvas.height/(window.devicePixelRatio||1):0; }

function _renderGraph(){
  if(!_gCtx||!_gCanvas) return;
  const dpr = window.devicePixelRatio||1;
  const W = _W(), H = _H();
  _gCtx.clearRect(0,0,W*dpr,H*dpr);

  // Empty state check
  const vis = _gNodes.filter(n=>n.visible);
  document.getElementById('gc-empty').style.display = vis.length===0?'block':'none';
  if(vis.length===0) return;

  _gCtx.save();
  _gCtx.scale(dpr,dpr);
  _gCtx.translate(_gPanX,_gPanY);
  _gCtx.scale(_gZoom,_gZoom);

  // Draw edges
  for(const e of _gEdges){
    if(!e.src||!e.tgt||!e.src.visible||!e.tgt.visible) continue;
    const connected = _gSelected&&(e.src===_gSelected||e.tgt===_gSelected);
    const dim = _gSelected&&!connected;
    const isWikilink = e.type==='related_to';
    const baseAlpha = e.inferred?0.2:isWikilink?0.45:0.32;
    const alpha = dim?0.04:connected?0.9:baseAlpha;

    _gCtx.beginPath();
    _gCtx.moveTo(e.src.x,e.src.y);
    _gCtx.lineTo(e.tgt.x,e.tgt.y);
    // Wikilinks: warm blue; hierarchy: neutral gray; inferred: muted
    if(isWikilink) _gCtx.strokeStyle = `rgba(88,166,255,${alpha})`;
    else if(e.inferred) _gCtx.strokeStyle = `rgba(139,148,158,${alpha})`;
    else _gCtx.strokeStyle = `rgba(100,120,140,${alpha})`;
    _gCtx.lineWidth = (e.inferred?1:isWikilink?1.5:1.2)/_gZoom;
    if(e.inferred) _gCtx.setLineDash([5/_gZoom,4/_gZoom]);
    else _gCtx.setLineDash([]);
    _gCtx.stroke();
  }
  _gCtx.setLineDash([]);

  // Pre-compute direct neighbors of selected node
  const _gNeighbors = new Set();
  if(_gSelected){
    for(const e of _gEdges){
      if(!e.src||!e.tgt) continue;
      if(e.src===_gSelected&&e.tgt.visible) _gNeighbors.add(e.tgt);
      if(e.tgt===_gSelected&&e.src.visible) _gNeighbors.add(e.src);
    }
  }

  // Draw nodes (larger first so small ones render on top)
  const sorted = [...vis].sort((a,b)=>b.radius-a.radius);
  const showLabel = _gZoom>0.35;

  for(const n of sorted){
    const isH = n===_gHovered;
    const isS = n===_gSelected;
    const isNeighbor = _gNeighbors.has(n);
    // Full dim only for nodes with no connection to selected
    const dim = _gSelected&&!isS&&!isH&&!isNeighbor;
    const col = GC[n.type]||GC.note;
    const r = n.radius;
    const isMatch = _gSearchQ&&n.label.toLowerCase().includes(_gSearchQ);

    // Glow for selected
    if(isS){
      _gCtx.shadowColor = col.stroke;
      _gCtx.shadowBlur = 18/_gZoom;
    }

    _gCtx.beginPath();
    _gCtx.arc(n.x,n.y,isH||isS?r+2:r,0,Math.PI*2);
    if(isS)           _gCtx.fillStyle = col.stroke;
    else if(isMatch)  _gCtx.fillStyle = col.stroke+'55';
    else if(isNeighbor) _gCtx.fillStyle = col.fill+'cc';  // neighbors: semi-bright
    else if(dim)      _gCtx.fillStyle = col.fill+'22';    // others: heavy fade
    else              _gCtx.fillStyle = col.fill;
    _gCtx.fill();

    if(isNeighbor)    _gCtx.strokeStyle = col.stroke+'88';
    else if(dim)      _gCtx.strokeStyle = `rgba(139,148,158,0.12)`;
    else              _gCtx.strokeStyle = isH||isS?col.stroke:col.stroke+'cc';
    _gCtx.lineWidth = (isS?3:isH?2.5:isNeighbor?2:1.5)/_gZoom;
    _gCtx.stroke();
    _gCtx.shadowBlur=0;

    // Non-canonical indicator: small purple dot
    if(!n.canonical){
      _gCtx.beginPath();
      _gCtx.arc(n.x+r*0.62,n.y-r*0.62,Math.max(2,3.5/_gZoom),0,Math.PI*2);
      _gCtx.fillStyle = dim?'rgba(110,64,201,0.12)':isNeighbor?'rgba(110,64,201,0.6)':'#6e40c9';
      _gCtx.fill();
    }

    // Labels: always for selected/hovered/neighbor; hide for fully dimmed
    if(isS||isH||isNeighbor||(showLabel&&!dim)){
      const fs = Math.min(13,Math.max(9,11/_gZoom));
      const bold = n.type==='project'||n.type==='branch' ? '600 ' : '';
      _gCtx.font = `${bold}${fs}px -apple-system,system-ui,sans-serif`;
      _gCtx.fillStyle = dim ? 'rgba(139,148,158,0.12)' : col.label;
      _gCtx.globalAlpha = isNeighbor ? 0.65 : 1.0;
      _gCtx.textAlign='center';
      _gCtx.textBaseline='top';
      _gCtx.fillText(n.label,n.x,n.y+r+Math.max(3,4/_gZoom));
      _gCtx.globalAlpha = 1.0;
    }
  }

  _gCtx.restore();
}

// ---- Mouse/touch handlers ----
function _screenToGraph(sx,sy){ return {x:(sx-_gPanX)/_gZoom, y:(sy-_gPanY)/_gZoom}; }

function _nodeAt(sx,sy){
  const gp = _screenToGraph(sx,sy);
  let best=null, bestD=Infinity;
  for(const n of _gNodes){
    if(!n.visible) continue;
    const dx=n.x-gp.x, dy=n.y-gp.y;
    const d=Math.sqrt(dx*dx+dy*dy);
    if(d<n.radius+6/_gZoom&&d<bestD){ best=n; bestD=d; }
  }
  return best;
}

function _rectOf(el){ return el.getBoundingClientRect(); }

function _onGDown(e){
  const r=_rectOf(_gCanvas);
  const sx=e.clientX-r.left, sy=e.clientY-r.top;
  const hit=_nodeAt(sx,sy);
  if(hit){ _gNodeDrag=hit; _gDragging=false; }
  else{ _gDragStart={x:sx,y:sy,px:_gPanX,py:_gPanY}; _gDragging=true; _gCanvas.classList.add('gdrag'); }
}

function _onGMove(e){
  const r=_rectOf(_gCanvas);
  const sx=e.clientX-r.left, sy=e.clientY-r.top;
  if(_gNodeDrag){
    const gp=_screenToGraph(sx,sy);
    _gNodeDrag.x=gp.x; _gNodeDrag.y=gp.y; _gNodeDrag.vx=0; _gNodeDrag.vy=0;
    _renderGraph(); return;
  }
  if(_gDragging&&_gDragStart){
    _gPanX=_gDragStart.px+(sx-_gDragStart.x);
    _gPanY=_gDragStart.py+(sy-_gDragStart.y);
    _renderGraph(); return;
  }
  const hit=_nodeAt(sx,sy);
  if(hit!==_gHovered){
    _gHovered=hit;
    _gCanvas.style.cursor=hit?'pointer':'grab';
    _renderGraph();
  }
}

function _onGUp(e){
  const wasDraggingNode = !!_gNodeDrag;
  _gNodeDrag=null; _gDragging=false; _gDragStart=null;
  _gCanvas.classList.remove('gdrag');
  // Let neighbours settle after a node drag
  if(wasDraggingNode&&!_simRunning){
    _simAlpha=0.3; _simRunning=true;
    if(_simFrame) cancelAnimationFrame(_simFrame);
    _simStep();
  }
}

function _onGClick(e){
  const r=_rectOf(_gCanvas);
  const sx=e.clientX-r.left, sy=e.clientY-r.top;
  const hit=_nodeAt(sx,sy);
  _gSelected=(hit&&hit===_gSelected)?null:hit;
  _updateInfoPanel();
  _renderGraph();
}

function _onGWheel(e){
  e.preventDefault();
  const r=_rectOf(_gCanvas);
  const sx=e.clientX-r.left, sy=e.clientY-r.top;
  const delta=e.deltaY<0?1.12:0.89;
  const nz=Math.max(0.08,Math.min(6,_gZoom*delta));
  _gPanX=sx-(sx-_gPanX)*(nz/_gZoom);
  _gPanY=sy-(sy-_gPanY)*(nz/_gZoom);
  _gZoom=nz;
  _renderGraph();
}

// ---- Graph controls ----
function graphZoomIn(){
  _gZoom=Math.min(6,_gZoom*1.25);
  _gPanX=_W()/2-((_W()/2-_gPanX)/_gZoom)*_gZoom;
  _gPanY=_H()/2-((_H()/2-_gPanY)/_gZoom)*_gZoom;
  _renderGraph();
}
function graphZoomOut(){
  const prev=_gZoom;
  _gZoom=Math.max(0.08,_gZoom/1.25);
  _gPanX=_W()/2-((_W()/2-_gPanX)/prev)*_gZoom;
  _gPanY=_H()/2-((_H()/2-_gPanY)/prev)*_gZoom;
  _renderGraph();
}
function resetGraphView(){
  const cnt=_gCanvas&&_gCanvas.parentElement;
  if(cnt){ _gPanX=cnt.clientWidth/2; _gPanY=cnt.clientHeight/2; }
  _gZoom=0.85;
  _computeLayout();
  _startSim();
}

function _applyFilters(){
  for(const n of _gNodes){
    n.visible = _gFilters.types.has(n.type)||n.type==='project';
    if(n.visible&&_gFilters.canonical==='canonical') n.visible=n.canonical;
    if(n.visible&&_gSearchQ) n.visible=n.label.toLowerCase().includes(_gSearchQ)||n.type==='project';
  }
  if(_gSelected&&!_gSelected.visible){ _gSelected=null; _updateInfoPanel(); }
  _startSim();
}

function _toggleType(type){
  const active = _gFilters.types.has(type);
  // Prevent deselecting all non-project types
  const others = ['branch','note','decision','evidence','output'].filter(t=>t!==type&&_gFilters.types.has(t));
  if(active&&others.length===0) return;
  if(active) _gFilters.types.delete(type); else _gFilters.types.add(type);
  document.querySelectorAll('.gf-btn').forEach(b=>{
    b.classList.toggle('active',_gFilters.types.has(b.dataset.type));
  });
  _applyFilters();
}

function _setCanonicalFilter(val){
  _gFilters.canonical=val;
  document.querySelectorAll('.gcf-btn').forEach(b=>{
    b.classList.toggle('active',b.dataset.val===val);
  });
  _applyFilters();
}

function _updateInfoPanel(){
  const panel=document.getElementById('gc-info');
  const body=document.getElementById('gc-info-body');
  if(!_gSelected||!panel){ panel&&panel.classList.remove('visible'); return; }
  const n=_gSelected;
  const col=GC[n.type]||GC.note;
  const openBtn = n.path
    ? `<button class="gi-open" onclick="nav('note','${esc(n.path)}')">Open note</button>`:'';
  body.innerHTML=`
    <div class="gi-type" style="color:${col.label}">${n.type}</div>
    <div class="gi-title">${esc(n.label)}</div>
    ${n.summary?`<div class="gi-summary">${esc(n.summary.substring(0,130))}${n.summary.length>130?'...':''}</div>`:''}
    <div class="gi-cn ${n.canonical?'ok':'nc'}">${n.canonical?'canonical (Memory)':'non-canonical'}</div>
    ${openBtn}`;
  panel.classList.add('visible');
}

function closeInfoPanel(){
  _gSelected=null;
  document.getElementById('gc-info').classList.remove('visible');
  _renderGraph();
}

// =========================================================================
// Boot
// =========================================================================
buildSidebar();
handleHash();
window.addEventListener('hashchange', handleHash);
</script>
</body>
</html>
"""


# --------------------------------------------------------------------------- #
# Site generation entry point                                                  #
# --------------------------------------------------------------------------- #


def generate_site(
    vault_dir: Path,
    output_dir: Path | None = None,
    *,
    dry_run: bool = False,
    include_evidence: bool = True,
    include_sessions: bool = False,
) -> dict[str, Any]:
    """Generate the static site (with graph) from the vault.

    Returns a summary dict:
      {"action": "created"|"updated"|"dry-run", "site_dir": str, ...}

    Writes:
      <output_dir>/index.html          -- main SPA with embedded graph view
      <output_dir>/data/knowledge.json -- structured knowledge data model
      <output_dir>/data/graph.json     -- graph nodes and edges
    """
    if output_dir is None:
        output_dir = resolve_site_output_dir(vault_dir)

    site_data = build_site_data(
        vault_dir,
        include_evidence=include_evidence,
        include_sessions=include_sessions,
    )
    graph_data = build_graph_data(site_data)

    if dry_run:
        return {
            "action": "dry-run",
            "site_dir": str(output_dir),
            "note_count": site_data["stats"]["note_count"],
            "branch_count": site_data["stats"]["branch_count"],
            "evidence_count": site_data["stats"]["evidence_count"],
            "decision_count": site_data["stats"]["decision_count"],
            "graph_node_count": graph_data["stats"]["node_count"],
            "graph_edge_count": graph_data["stats"]["edge_count"],
            "dry_run": True,
        }

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "data").mkdir(exist_ok=True)

    # Write knowledge.json
    json_path = output_dir / "data" / "knowledge.json"
    json_existed = json_path.exists()
    json_path.write_text(json.dumps(site_data, indent=2, ensure_ascii=False), encoding="utf-8")

    # Write graph.json
    graph_path = output_dir / "data" / "graph.json"
    graph_path.write_text(json.dumps(graph_data, indent=2, ensure_ascii=False), encoding="utf-8")

    # Build and write index.html
    html_content = _render_html(site_data, graph_data)
    html_path = output_dir / "index.html"
    html_existed = html_path.exists()
    html_path.write_text(html_content, encoding="utf-8")

    action = "updated" if (json_existed or html_existed) else "created"

    return {
        "action": action,
        "site_dir": str(output_dir),
        "index_html": str(html_path),
        "knowledge_json": str(json_path),
        "graph_json": str(graph_path),
        "note_count": site_data["stats"]["note_count"],
        "branch_count": site_data["stats"]["branch_count"],
        "evidence_count": site_data["stats"]["evidence_count"],
        "decision_count": site_data["stats"]["decision_count"],
        "graph_node_count": graph_data["stats"]["node_count"],
        "graph_edge_count": graph_data["stats"]["edge_count"],
        "dry_run": False,
    }


def _render_html(data: dict[str, Any], graph_data: dict[str, Any] | None = None) -> str:
    """Render the complete index.html with data and graph data embedded."""
    if graph_data is None:
        graph_data = {"nodes": [], "edges": [], "stats": {"node_count": 0, "edge_count": 0}}

    project_name = html_mod.escape(data["project"].get("name", "Knowledge Vault"))
    generated = data.get("generated", "")

    data_json = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    graph_json = json.dumps(graph_data, ensure_ascii=False, separators=(",", ":"))

    return (
        _HTML_TEMPLATE
        .replace("__PROJECT_NAME__", project_name)
        .replace("__GENERATED__", generated)
        .replace("__DATA_JSON__", data_json)
        .replace("__GRAPH_JSON__", graph_json)
    )
