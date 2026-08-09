"""Local browser viewer for bedrock vaults.

Generates a self-contained HTML file that shows:
  - Project summary / STATUS
  - Ontology tree by folder
  - Rendered markdown note content
  - Note type badges (Memory / Evidence / Outputs / Sessions)
  - Search / filter
  - Clear visual separation between canonical and non-canonical notes

No external dependencies. No Obsidian required.
"""

from __future__ import annotations

import datetime
import html
import json
import re
from pathlib import Path
from typing import Any

from .index import build_index, _extract_frontmatter


_BADGE_COLORS = {
    "Memory": "#2d6a4f",
    "Evidence": "#4a4e69",
    "Outputs": "#6b4226",
    "Sessions": "#3d405b",
}

_FOLDER_ORDER = ["Memory", "Evidence", "Outputs", "Sessions"]


def _md_to_html(text: str) -> str:
    """Minimal but correct markdown-to-HTML renderer."""
    # Strip frontmatter
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end >= 0:
            text = text[end + 4:].lstrip("\n")

    lines = text.split("\n")
    out: list[str] = []
    in_code = False
    in_ul = False
    code_buf: list[str] = []

    def flush_ul() -> None:
        nonlocal in_ul
        if in_ul:
            out.append("</ul>")
            in_ul = False

    def inline(s: str) -> str:
        s = html.escape(s)
        s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"\*(.+?)\*", r"<em>\1</em>", s)
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
        return s

    for line in lines:
        if line.startswith("```"):
            flush_ul()
            if in_code:
                out.append(html.escape("\n".join(code_buf)))
                out.append("</code></pre>")
                code_buf = []
                in_code = False
            else:
                lang = line[3:].strip()
                cls = f' class="lang-{lang}"' if lang else ""
                out.append(f"<pre><code{cls}>")
                in_code = True
            continue

        if in_code:
            code_buf.append(line)
            continue

        if line.startswith("> "):
            flush_ul()
            out.append(f"<blockquote>{inline(line[2:])}</blockquote>")
        elif line.startswith("### "):
            flush_ul()
            out.append(f"<h3>{html.escape(line[4:])}</h3>")
        elif line.startswith("## "):
            flush_ul()
            out.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("# "):
            flush_ul()
            out.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith(("- ", "* ")):
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{inline(line[2:])}</li>")
        elif line.strip() == "" or line.strip() == "---":
            flush_ul()
            out.append("<br>")
        else:
            flush_ul()
            out.append(f"<p>{inline(line)}</p>")

    flush_ul()
    if in_code:
        out.append(html.escape("\n".join(code_buf)))
        out.append("</code></pre>")

    return "\n".join(out)


def _read_status(vault_dir: Path) -> dict[str, str]:
    status_file = vault_dir / "STATUS.md"
    if not status_file.is_file():
        return {}
    fm = _extract_frontmatter(status_file.read_text(encoding="utf-8", errors="replace"))
    return fm


def _collect_notes(vault_dir: Path) -> list[dict[str, Any]]:
    index = build_index(vault_dir)
    notes_meta = index["notes"]
    result: list[dict[str, Any]] = []

    for meta in notes_meta:
        rel = meta["path"]
        p = vault_dir / rel
        try:
            raw = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            raw = ""
        result.append(
            {
                "path": rel,
                "title": meta["title"],
                "note_type": meta["note_type"],
                "area": meta["area"],
                "canonical": meta["canonical"],
                "folder": meta["folder"],
                "is_branch_entry": meta["is_branch_entry"],
                "summary": meta["summary"],
                "html": _md_to_html(raw),
            }
        )
    return result


_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>bedrock: {project}</title>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --bg:#0f1117;--sidebar-bg:#161b22;--border:#30363d;
  --text:#e6edf3;--muted:#8b949e;--accent:#58a6ff;
  --canonical:#2d6a4f;--evidence:#4a4e69;--output:#6b4226;--session:#3d405b;
  --code-bg:#161b22;--hover:#1f2937;
}}
body{{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:14px;line-height:1.6;height:100vh;display:flex;flex-direction:column;overflow:hidden}}
#topbar{{background:var(--sidebar-bg);border-bottom:1px solid var(--border);padding:10px 16px;display:flex;align-items:center;gap:12px;flex-shrink:0}}
#topbar h1{{font-size:15px;font-weight:600;color:var(--accent)}}
#topbar .meta{{font-size:12px;color:var(--muted);margin-left:auto}}
#search{{background:#0f1117;border:1px solid var(--border);border-radius:6px;color:var(--text);padding:5px 10px;font-size:13px;width:220px;outline:none}}
#search:focus{{border-color:var(--accent)}}
#app{{display:flex;flex:1;overflow:hidden}}
#sidebar{{width:280px;min-width:200px;background:var(--sidebar-bg);border-right:1px solid var(--border);overflow-y:auto;flex-shrink:0;padding:8px 0}}
#main{{flex:1;overflow-y:auto;padding:24px 32px}}
.tree-folder{{margin-bottom:4px}}
.folder-header{{padding:4px 12px;font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);display:flex;align-items:center;gap:6px;cursor:pointer;user-select:none}}
.folder-header:hover{{color:var(--text)}}
.folder-badge{{display:inline-block;padding:1px 6px;border-radius:3px;font-size:10px;font-weight:600;text-transform:uppercase}}
.folder-children{{padding-left:12px}}
.tree-item{{padding:4px 12px 4px 20px;cursor:pointer;border-radius:4px;color:var(--muted);font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;display:flex;align-items:center;gap:6px}}
.tree-item:hover{{background:var(--hover);color:var(--text)}}
.tree-item.active{{background:var(--hover);color:var(--accent)}}
.tree-item.branch-entry{{font-weight:600;color:var(--text)}}
.note-badge{{display:inline-block;padding:1px 6px;border-radius:3px;font-size:10px;font-weight:600;text-transform:uppercase;flex-shrink:0}}
.badge-Memory{{background:var(--canonical);color:#d8f3dc}}
.badge-Evidence{{background:var(--evidence);color:#c5c6e8}}
.badge-Outputs{{background:var(--output);color:#f4d9c6}}
.badge-Sessions{{background:var(--session);color:#c5c6e8}}
#note-header{{margin-bottom:20px;padding-bottom:16px;border-bottom:1px solid var(--border)}}
#note-header h1{{font-size:22px;font-weight:700;margin-bottom:8px}}
#note-meta-row{{display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-size:12px;color:var(--muted)}}
#note-path{{font-family:monospace;font-size:11px;color:var(--muted)}}
.non-canonical-warning{{background:#2a1f1a;border:1px solid #6b4226;border-radius:6px;padding:8px 12px;margin-bottom:16px;font-size:12px;color:#f4d9c6}}
#note-body h1{{font-size:20px;font-weight:700;margin:16px 0 8px}}
#note-body h2{{font-size:16px;font-weight:600;margin:16px 0 6px;color:#cdd9e5;padding-bottom:4px;border-bottom:1px solid var(--border)}}
#note-body h3{{font-size:14px;font-weight:600;margin:12px 0 4px;color:#cdd9e5}}
#note-body p{{margin:6px 0;color:var(--text)}}
#note-body ul{{margin:6px 0 6px 20px}}
#note-body li{{margin:2px 0}}
#note-body code{{background:var(--code-bg);border:1px solid var(--border);border-radius:3px;padding:1px 5px;font-family:monospace;font-size:12px}}
#note-body pre{{background:var(--code-bg);border:1px solid var(--border);border-radius:6px;padding:12px;overflow-x:auto;margin:10px 0}}
#note-body pre code{{background:none;border:none;padding:0;font-size:12px}}
#note-body blockquote{{border-left:3px solid var(--accent);padding-left:12px;color:var(--muted);margin:8px 0}}
#note-body a{{color:var(--accent)}}
#placeholder{{color:var(--muted);text-align:center;margin-top:80px}}
.hidden{{display:none}}
</style>
</head>
<body>
<div id="topbar">
  <h1>bedrock</h1>
  <span style="color:var(--muted);font-size:13px">{project}</span>
  <input type="search" id="search" placeholder="Filter notes...">
  <span class="meta">Onboarding: {onboarding} &nbsp;|&nbsp; Generated: {generated}</span>
</div>
<div id="app">
  <nav id="sidebar"></nav>
  <main id="main">
    <div id="placeholder">Select a note from the tree to read it.</div>
    <div id="note-view" class="hidden">
      <div id="note-header">
        <div id="note-meta-row"></div>
        <h1 id="note-title"></h1>
        <div id="note-path"></div>
      </div>
      <div id="non-canonical-warning" class="non-canonical-warning hidden">
        This note is in <strong id="nc-folder"></strong> and is not canonical memory.
        It should not be treated as source of truth.
      </div>
      <div id="note-body"></div>
    </div>
  </main>
</div>
<script>
const DATA = {data};

const sidebar = document.getElementById('sidebar');
const noteView = document.getElementById('note-view');
const placeholder = document.getElementById('placeholder');
const searchInput = document.getElementById('search');

let activeItem = null;

function badge(folder) {{
  return `<span class="note-badge badge-${{folder}}">${{folder}}</span>`;
}}

function buildTree(notes) {{
  const groups = {{}};
  for (const n of notes) {{
    if (!groups[n.folder]) groups[n.folder] = [];
    groups[n.folder].push(n);
  }}
  const order = ['Memory','Evidence','Outputs','Sessions'];
  sidebar.innerHTML = '';
  for (const folder of order) {{
    if (!groups[folder]) continue;
    const div = document.createElement('div');
    div.className = 'tree-folder';
    div.dataset.folder = folder;
    const header = document.createElement('div');
    header.className = 'folder-header';
    header.innerHTML = `${{folder}} ${{badge(folder)}}`;
    header.onclick = () => children.classList.toggle('hidden');
    const children = document.createElement('div');
    children.className = 'folder-children';
    for (const note of groups[folder]) {{
      const item = document.createElement('div');
      item.className = 'tree-item' + (note.is_branch_entry ? ' branch-entry' : '');
      item.dataset.path = note.path;
      const name = note.path.split('/').pop().replace('.md','');
      item.innerHTML = `${{badge(folder)}} ${{escHtml(note.title || name)}}`;
      item.title = note.path;
      item.onclick = () => showNote(note, item);
      children.appendChild(item);
    }}
    div.appendChild(header);
    div.appendChild(children);
    sidebar.appendChild(div);
  }}
}}

function showNote(note, itemEl) {{
  if (activeItem) activeItem.classList.remove('active');
  activeItem = itemEl;
  itemEl.classList.add('active');
  placeholder.classList.add('hidden');
  noteView.classList.remove('hidden');
  document.getElementById('note-title').textContent = note.title;
  document.getElementById('note-path').textContent = note.path;
  document.getElementById('note-meta-row').innerHTML = badge(note.folder) +
    (note.note_type !== 'unknown' ? ` <span style="color:var(--muted)">${{escHtml(note.note_type)}}</span>` : '');
  const warn = document.getElementById('non-canonical-warning');
  if (!note.canonical) {{
    document.getElementById('nc-folder').textContent = note.folder;
    warn.classList.remove('hidden');
  }} else {{
    warn.classList.add('hidden');
  }}
  document.getElementById('note-body').innerHTML = note.html;
}}

function filterNotes(q) {{
  const ql = q.toLowerCase();
  const filtered = ql ? DATA.notes.filter(n =>
    n.title.toLowerCase().includes(ql) ||
    n.path.toLowerCase().includes(ql) ||
    (n.summary || '').toLowerCase().includes(ql)
  ) : DATA.notes;
  buildTree(filtered);
}}

function escHtml(s) {{
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}}

searchInput.addEventListener('input', e => filterNotes(e.target.value));
buildTree(DATA.notes);
</script>
</body>
</html>
"""


def export_html(vault_dir: Path, output_path: Path | None = None, *, dry_run: bool = False) -> tuple[Path, str]:
    """Generate a standalone HTML viewer for the vault.

    Returns (path, action) where action is 'created', 'exists', or 'dry-run'.
    """
    if output_path is None:
        output_path = vault_dir / "Outputs" / "knowledge-export.html"

    if dry_run:
        return output_path, "dry-run"

    notes = _collect_notes(vault_dir)
    status = _read_status(vault_dir)

    project = status.get("project", vault_dir.name)
    onboarding = status.get("onboarding", "unknown")
    generated = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    data_json = json.dumps(
        {
            "project": project,
            "onboarding": onboarding,
            "generated": generated,
            "notes": notes,
        },
        ensure_ascii=False,
    )

    content = _HTML_TEMPLATE.format(
        project=html.escape(project),
        onboarding=html.escape(onboarding),
        generated=generated,
        data=data_json,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    existed = output_path.exists()
    output_path.write_text(content, encoding="utf-8")
    action = "updated" if existed else "created"
    return output_path, action


def open_viewer(vault_dir: Path) -> Path:
    """Export HTML and open it in the default browser.

    Returns the export path; on a headless box or over SSH the browser is
    skipped, since the export itself is the part that matters.
    """
    from .shell import open_in_browser

    path, _ = export_html(vault_dir)
    open_in_browser(path.as_uri())
    return path
