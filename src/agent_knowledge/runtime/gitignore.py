"""The .gitignore patterns bedrock owns in a connected project.

Everything listed here is regenerated per machine or per run, so committing it
only tells the next developer which machine last touched the repo. Files that
are generated but machine-*independent* — `.claude/settings.json`,
`.cursor/hooks.json`, `.claude/CLAUDE.md`, `.cursor/rules/` — are deliberately
absent: sharing those is what makes a fresh clone work.
"""

from __future__ import annotations

from pathlib import Path

_HEADER_LINE = "# bedrock: noisy auto-generated content excluded from git"
_HEADER = (
    f"{_HEADER_LINE}\n"
    "# Curated knowledge (Memory/, Work/, History/, Evidence/imports/) IS tracked.\n"
)

PATTERNS: tuple[str, ...] = (
    "bedrock/Evidence/raw/",
    "bedrock/Views/site/",
    "bedrock/Views/graph/*.json",
    "bedrock/Views/graph/*.md",
    "bedrock/Views/graph/*.canvas",
    "bedrock/Outputs/absorb-manifest.md",
    "bedrock/.obsidian/workspace",
    "bedrock/.obsidian/workspace.json",
    "bedrock/.obsidian/workspaces.json",
    # Run artifact: records the absolute project path of whoever ran the sync.
    ".cursor/knowledge-sync.last.json",
)


def missing_patterns(text: str) -> list[str]:
    """Patterns absent from the given .gitignore contents, in canonical order."""
    present = {line.strip() for line in text.splitlines()}
    return [p for p in PATTERNS if p not in present]


def ensure_patterns(repo_path: Path, *, dry_run: bool = False) -> list[str]:
    """Append the bedrock-owned patterns a project's .gitignore lacks.

    Reconciles pattern by pattern rather than all-or-nothing, so a project
    connected by an older bedrock picks up patterns added since. Returns the
    patterns that were missing (whether or not they were written).
    """
    gitignore = repo_path / ".gitignore"
    text = gitignore.read_text(encoding="utf-8") if gitignore.is_file() else ""
    missing = missing_patterns(text)
    if not missing or dry_run:
        return missing

    block = "\n".join(missing) + "\n"
    if _HEADER_LINE not in text:
        block = _HEADER + block
    merged = (text.rstrip("\n") + "\n\n" + block) if text.strip() else block
    gitignore.write_text(merged, encoding="utf-8")
    return missing
