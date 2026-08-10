"""Read and write fields in a markdown file's YAML frontmatter.

Lives in its own module so both refresh.py and migrations.py can use it without
importing each other.
"""

from __future__ import annotations

import re


def fm_get(text: str, key: str) -> str:
    """Read a field from YAML frontmatter."""
    if not text.startswith("---"):
        return ""
    end = text.find("\n---", 3)
    if end < 0:
        return ""
    m = re.search(rf"^{re.escape(key)}:\s*(.+)$", text[4:end], re.MULTILINE)
    return m.group(1).strip().strip("\"'") if m else ""


def fm_set(text: str, key: str, value: str) -> str:
    """Add or update a field in YAML frontmatter."""
    if not text.startswith("---"):
        # No frontmatter — don't add one silently
        return text
    end = text.find("\n---", 3)
    if end < 0:
        return text
    fm_body = text[4:end]
    rest = text[end + 4:]
    pattern = rf"^{re.escape(key)}:.*$"
    if re.search(pattern, fm_body, re.MULTILINE):
        fm_body = re.sub(pattern, f"{key}: {value}", fm_body, flags=re.MULTILINE)
    else:
        fm_body = fm_body.rstrip("\n") + f"\n{key}: {value}\n"
    return f"---\n{fm_body}\n---{rest}"
