"""Clean web import for bedrock vaults.

Imports a URL or local HTML file as cleaned markdown evidence into
Evidence/imports/. Strips navigation, ads, scripts, and boilerplate.
Produces a note clearly marked non-canonical.

Uses only Python stdlib: urllib, html.parser, re.
No external HTTP client or HTML parsing library required.
"""

from __future__ import annotations

import datetime
import hashlib
import re
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Sequence

_SKIP_TAGS: frozenset[str] = frozenset(
    {
        "script", "style", "nav", "header", "footer", "aside",
        "form", "button", "select", "option", "menu", "noscript",
        "iframe", "svg", "path", "canvas", "figure",
        "template", "dialog", "details",
    }
)

_HEADING_TAGS: frozenset[str] = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_LIST_ITEM_TAGS: frozenset[str] = frozenset({"li"})
_BLOCK_TAGS: frozenset[str] = frozenset({"p", "div", "section", "article", "main", "blockquote", "tr", "td", "th"})


class _Extractor(HTMLParser):
    """Stateful HTML-to-markdown extractor."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._pre_depth = 0
        self._code_depth = 0
        self._parts: list[str] = []
        self._current_heading: str | None = None
        self._current_href: str | None = None
        self._link_text_parts: list[str] = []
        self._in_link = False

    # --- tag handlers -------------------------------------------------------

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._skip_depth > 0:
            self._skip_depth += 1
            return
        if tag in _SKIP_TAGS:
            self._skip_depth = 1
            return

        attr_dict = dict(attrs)

        if tag == "pre":
            self._pre_depth += 1
            self._parts.append("\n```\n")
        elif tag == "code":
            self._code_depth += 1
            if self._pre_depth == 0:
                self._parts.append("`")
        elif tag in _HEADING_TAGS:
            level = int(tag[1])
            self._current_heading = "#" * level
            self._parts.append(f"\n{'#' * level} ")
        elif tag == "p":
            self._parts.append("\n")
        elif tag == "li":
            self._parts.append("\n- ")
        elif tag == "ul" or tag == "ol":
            self._parts.append("\n")
        elif tag == "blockquote":
            self._parts.append("\n> ")
        elif tag == "br":
            self._parts.append("\n")
        elif tag == "hr":
            self._parts.append("\n---\n")
        elif tag == "a":
            href = attr_dict.get("href", "")
            if href and href.startswith(("http://", "https://", "/")):
                self._in_link = True
                self._current_href = href
                self._link_text_parts = []
        elif tag in ("strong", "b"):
            self._parts.append("**")
        elif tag in ("em", "i"):
            self._parts.append("*")
        elif tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self._skip_depth > 0:
            self._skip_depth -= 1
            return

        if tag == "pre":
            self._pre_depth -= 1
            self._parts.append("\n```\n")
        elif tag == "code":
            self._code_depth -= 1
            if self._pre_depth == 0:
                self._parts.append("`")
        elif tag in _HEADING_TAGS:
            self._current_heading = None
            self._parts.append("\n")
        elif tag in ("p", "div", "section", "article", "main", "li", "tr"):
            self._parts.append("\n")
        elif tag == "blockquote":
            self._parts.append("\n")
        elif tag == "a":
            if self._in_link and self._current_href and self._link_text_parts:
                text = "".join(self._link_text_parts).strip()
                if text:
                    self._parts.append(f"[{text}]({self._current_href})")
            self._in_link = False
            self._current_href = None
            self._link_text_parts = []
        elif tag in ("strong", "b"):
            self._parts.append("**")
        elif tag in ("em", "i"):
            self._parts.append("*")

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        if self._in_link:
            self._link_text_parts.append(data)
        else:
            self._parts.append(data)

    def get_markdown(self) -> str:
        return "".join(self._parts)


def _clean_markdown(raw: str) -> str:
    """Post-process extracted markdown: collapse whitespace, remove junk lines."""
    # Normalise line endings
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    # Collapse 3+ blank lines to 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Remove lines that are just whitespace
    lines = [line.rstrip() for line in text.split("\n")]
    # Strip common boilerplate patterns (cookie notices, share links, etc.)
    junk_patterns = [
        re.compile(r"^(share|tweet|copy link|subscribe|newsletter|cookie|accept|decline|privacy policy)[\s.!]*$", re.IGNORECASE),
        re.compile(r"^\s*\|?\s*\[?\s*(home|about|contact|login|sign up|sign in|menu)\s*\]?\s*\|?\s*$", re.IGNORECASE),
    ]
    cleaned: list[str] = []
    for line in lines:
        if any(p.match(line.strip()) for p in junk_patterns):
            continue
        cleaned.append(line)
    text = "\n".join(cleaned)
    # One more pass to collapse extra blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_html_title(html_content: str) -> str:
    import html as html_mod

    m = re.search(r"<title[^>]*>([^<]+)</title>", html_content, re.IGNORECASE)
    if m:
        return html_mod.unescape(m.group(1).strip())
    m = re.search(r"<h1[^>]*>([^<]+)</h1>", html_content, re.IGNORECASE)
    if m:
        return html_mod.unescape(m.group(1).strip())
    return ""


def _extract_md_title(text: str) -> str:
    """Extract title from the first ATX heading in markdown/plaintext."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
        if stripped.startswith("## "):
            return stripped[3:].strip()
    return ""


def _is_html(content: str) -> bool:
    snip = content.lstrip()[:200].lower()
    return snip.startswith("<!doctype") or snip.startswith("<html") or "<head" in snip or "<body" in snip


def html_to_markdown(content: str) -> tuple[str, str]:
    """Convert HTML (or plain text/markdown) to clean markdown.

    Returns (title, markdown_body). Handles both HTML pages and raw
    text/markdown files without requiring full HTML structure.
    """
    if _is_html(content):
        title = _extract_html_title(content)
        extractor = _Extractor()
        extractor.feed(content)
        body = _clean_markdown(extractor.get_markdown())
    else:
        # Plain text or markdown -- pass through with minimal cleanup
        title = _extract_md_title(content)
        body = _clean_markdown(content)
    return title, body


def fetch_url(url: str, *, timeout: int = 15) -> str:
    """Fetch a URL and return the HTML content. Stdlib only."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "project-bedrock/import (https://github.com/robotaitai/project-bedrock)",
            "Accept": "text/html,application/xhtml+xml,*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        charset = "utf-8"
        content_type = resp.headers.get("Content-Type", "")
        if "charset=" in content_type:
            charset = content_type.split("charset=")[-1].strip().split(";")[0].strip()
        return raw.decode(charset, errors="replace")


def _slugify(text: str) -> str:
    s = text.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")[:60]


def clean_import(
    source: str,
    output_dir: Path,
    *,
    slug: str | None = None,
    dry_run: bool = False,
) -> tuple[Path, str, str]:
    """Import source (URL or file path) as cleaned markdown evidence.

    Returns (output_path, action, title).
    action is 'created', 'exists', or 'dry-run'.
    """
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    date_str = datetime.date.today().isoformat()

    # Fetch content
    if source.startswith(("http://", "https://")):
        html_content = fetch_url(source)
        source_label = source
    else:
        p = Path(source)
        if not p.is_file():
            raise FileNotFoundError(f"Source file not found: {source}")
        html_content = p.read_text(encoding="utf-8", errors="replace")
        source_label = p.name

    title, body = html_to_markdown(html_content)
    if not title:
        # Derive a readable title from the URL path or filename, not the full URL
        if source_label.startswith(("http://", "https://")):
            path_part = source_label.rstrip("/").rsplit("/", 1)[-1]
            path_part = re.sub(r"\.[a-z]+$", "", path_part)  # strip extension
        else:
            path_part = Path(source_label).stem
        title = _slugify(path_part).replace("-", " ").title() or "Imported Page"

    if not slug:
        slug = f"{date_str}-{_slugify(title or source_label)}"

    output_path = output_dir / f"{slug}.md"

    # Idempotency: if same output path exists, check content hash
    content_id = hashlib.sha256(body.encode()).hexdigest()[:12]
    if not dry_run and output_path.exists():
        existing = output_path.read_text(encoding="utf-8", errors="replace")
        if content_id in existing:
            return output_path, "exists", title

    note = (
        "---\n"
        "note_type: evidence\n"
        f"source: {source_label}\n"
        f"title: {title}\n"
        f"imported: {timestamp}\n"
        f"content_id: {content_id}\n"
        "canonical: false\n"
        "---\n"
        "\n"
        f"# {title}\n"
        "\n"
        f"> Imported from: {source_label}  \n"
        f"> Date: {date_str}  \n"
        f"> This is non-canonical evidence. Verify before promoting facts to Memory/.\n"
        "\n"
        f"{body}\n"
    )

    if dry_run:
        return output_path, "dry-run", title

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path.write_text(note, encoding="utf-8")
    return output_path, "created", title
