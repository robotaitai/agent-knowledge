"""Guards against using stdlib APIs newer than the declared requires-python.

CI is the only place 3.9 actually runs, so a 3.10+ call slips through every
local test run and every review. These checks fail on any interpreter.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"


def _calls(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            yield node


def _keyword_names(node: ast.Call) -> set[str]:
    return {kw.arg for kw in node.keywords if kw.arg}


def test_no_write_text_newline_kwarg():
    """Path.write_text() gained `newline` in 3.10; this project supports 3.9.

    Use path.open("w", encoding=..., newline="\\n") instead -- open() has
    accepted newline since forever.
    """
    offenders: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for call in _calls(tree):
            func = call.func
            if isinstance(func, ast.Attribute) and func.attr in ("write_text", "read_text"):
                if "newline" in _keyword_names(call):
                    offenders.append(f"{path.relative_to(SRC)}:{call.lineno}")

    assert not offenders, (
        "Path.write_text()/read_text() only accept `newline` on Python 3.10+, "
        f"but this project declares requires-python >=3.9: {offenders}"
    )
