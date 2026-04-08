#!/usr/bin/env python3
"""
Estimate repo-controlled context savings from scoped project memory.

This tool measures only the text files you choose to include. It does not attempt
to model provider-side hidden tokens, tool-call overhead, or system prompts.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

SKIP_DIR_NAMES = {
    ".git",
    ".next",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "vendor",
}


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def json_dump(data: object) -> str:
    return json.dumps(data, indent=2, sort_keys=False)


def load_path_list(list_file: str | None) -> list[str]:
    if not list_file:
        return []
    path = Path(list_file).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"Path list file not found: {path}")
    items: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        items.append(line)
    return items


def unique_paths(paths: Iterable[Path]) -> list[Path]:
    seen: set[str] = set()
    ordered: list[Path] = []
    for path in paths:
        resolved = str(path)
        if resolved in seen:
            continue
        seen.add(resolved)
        ordered.append(path)
    return ordered


def expand_inputs(raw_inputs: list[str]) -> tuple[list[Path], list[str]]:
    files: list[Path] = []
    warnings: list[str] = []

    for raw in raw_inputs:
        path = Path(raw).expanduser()
        if not path.exists():
            warnings.append(f"Missing path skipped: {path}")
            continue
        if path.is_file():
            files.append(path)
            continue
        if path.is_dir():
            for root, dirnames, filenames in os.walk(path):
                dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIR_NAMES)
                for filename in sorted(filenames):
                    file_path = Path(root) / filename
                    if file_path.is_file():
                        files.append(file_path)
            continue
        warnings.append(f"Unsupported path type skipped: {path}")

    return unique_paths(sorted(files)), warnings


def is_binary_file(path: Path) -> bool:
    try:
        chunk = path.read_bytes()[:8192]
    except OSError:
        return True
    return b"\0" in chunk


class TokenCounter:
    def __init__(self, strategy: str) -> None:
        self.requested_strategy = strategy
        self.strategy = strategy
        self.estimate_only = True
        self.note = "Estimated using a 4-characters-per-token heuristic."
        self._encoder = None

        if strategy in {"auto", "tiktoken-cl100k"}:
            try:
                import tiktoken  # type: ignore

                self._encoder = tiktoken.get_encoding("cl100k_base")
                self.strategy = "tiktoken-cl100k"
                self.estimate_only = False
                self.note = "Measured with tiktoken cl100k_base. Still excludes provider-side hidden tokens."
            except Exception:
                if strategy == "tiktoken-cl100k":
                    raise RuntimeError(
                        "tiktoken-cl100k was requested, but tiktoken is not available."
                    )
                self.strategy = "chars4-estimate"
                self.estimate_only = True
                self.note = (
                    "Estimated using a 4-characters-per-token heuristic because tiktoken is unavailable."
                )
        elif strategy != "chars4-estimate":
            raise ValueError(f"Unsupported tokenizer strategy: {strategy}")

    def count(self, text: str) -> int:
        if self._encoder is not None:
            return len(self._encoder.encode(text))
        return int(math.ceil(len(text) / 4.0))


@dataclass
class Measurement:
    paths: list[str]
    file_count: int
    token_count: int
    byte_count: int
    binary_skipped: list[str]
    missing: list[str]


def relative_or_absolute(path: Path, project_root: Path | None) -> str:
    if project_root is None:
        return str(path)
    candidates = [path.absolute()]
    roots = [project_root.absolute()]

    try:
        candidates.append(path.resolve())
    except Exception:
        pass
    try:
        roots.append(project_root.resolve())
    except Exception:
        pass

    for candidate in candidates:
        for root in roots:
            try:
                return str(candidate.relative_to(root))
            except Exception:
                continue

    return str(path)


def measure_paths(
    counter: TokenCounter, files: list[Path], project_root: Path | None
) -> Measurement:
    token_count = 0
    byte_count = 0
    binary_skipped: list[str] = []
    missing: list[str] = []
    included_paths: list[str] = []

    for path in files:
        if not path.exists():
            missing.append(relative_or_absolute(path, project_root))
            continue
        if is_binary_file(path):
            binary_skipped.append(relative_or_absolute(path, project_root))
            continue

        try:
            raw_bytes = path.read_bytes()
            text = raw_bytes.decode("utf-8", errors="ignore")
        except OSError:
            missing.append(relative_or_absolute(path, project_root))
            continue

        token_count += counter.count(text)
        byte_count += len(raw_bytes)
        included_paths.append(relative_or_absolute(path, project_root))

    return Measurement(
        paths=included_paths,
        file_count=len(included_paths),
        token_count=token_count,
        byte_count=byte_count,
        binary_skipped=binary_skipped,
        missing=missing,
    )


def resolve_measurement_dir(project: str | None) -> Path:
    project_root = Path(project or ".").expanduser().absolute()
    knowledge_outputs = project_root / "agent-knowledge" / "Outputs" / "token-measurements"
    if knowledge_outputs.parent.exists():
        return knowledge_outputs
    return project_root / "token-measurements"


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_output(path: str | None, payload: dict) -> None:
    if not path:
        return
    dst = Path(path).expanduser()
    ensure_parent(dst)
    dst.write_text(json_dump(payload) + "\n", encoding="utf-8")


def build_compare_payload(
    args: argparse.Namespace, counter: TokenCounter
) -> dict:
    project_root = Path(args.project).expanduser().absolute() if args.project else None
    baseline_inputs = list(args.baseline or []) + load_path_list(args.baseline_list)
    optimized_inputs = list(args.optimized or []) + load_path_list(args.optimized_list)

    if not baseline_inputs:
        raise ValueError("At least one baseline path is required.")
    if not optimized_inputs:
        raise ValueError("At least one optimized path is required.")

    baseline_files, baseline_warnings = expand_inputs(baseline_inputs)
    optimized_files, optimized_warnings = expand_inputs(optimized_inputs)

    baseline = measure_paths(counter, baseline_files, project_root)
    optimized = measure_paths(counter, optimized_files, project_root)

    absolute_savings = baseline.token_count - optimized.token_count
    percentage_savings = 0.0
    if baseline.token_count > 0:
        percentage_savings = round((absolute_savings / baseline.token_count) * 100.0, 2)

    return {
        "mode": "static-compare",
        "generated_at": now_utc(),
        "project_root": str(project_root) if project_root else None,
        "tokenizer": {
            "strategy": counter.strategy,
            "estimate_only": counter.estimate_only,
            "note": counter.note,
        },
        "baseline": {
            "file_count": baseline.file_count,
            "token_count": baseline.token_count,
            "byte_count": baseline.byte_count,
            "paths": baseline.paths,
            "binary_skipped": baseline.binary_skipped,
            "missing": baseline.missing,
        },
        "optimized": {
            "file_count": optimized.file_count,
            "token_count": optimized.token_count,
            "byte_count": optimized.byte_count,
            "paths": optimized.paths,
            "binary_skipped": optimized.binary_skipped,
            "missing": optimized.missing,
        },
        "absolute_savings": absolute_savings,
        "percentage_savings": percentage_savings,
        "warnings": baseline_warnings + optimized_warnings,
        "measurement_scope": "Repo-controlled context only. Hidden provider tokens are not included.",
    }


def build_log_entry(args: argparse.Namespace, counter: TokenCounter) -> tuple[dict, Path]:
    project_root = Path(args.project or ".").expanduser().absolute()
    inputs = list(args.context or []) + load_path_list(args.context_list)
    if not inputs:
        raise ValueError("At least one context path is required for log-run.")

    files, warnings = expand_inputs(inputs)
    measurement = measure_paths(counter, files, project_root)
    log_path = (
        Path(args.log_file).expanduser()
        if args.log_file
        else resolve_measurement_dir(args.project) / "task-run-log.jsonl"
    )

    entry = {
        "logged_at": now_utc(),
        "task": args.task,
        "mode": args.mode,
        "project_root": str(project_root),
        "tokenizer": {
            "strategy": counter.strategy,
            "estimate_only": counter.estimate_only,
        },
        "token_count": measurement.token_count,
        "file_count": measurement.file_count,
        "byte_count": measurement.byte_count,
        "context_paths": measurement.paths,
        "binary_skipped": measurement.binary_skipped,
        "missing": measurement.missing,
        "notes": args.notes or "",
        "warnings": warnings,
    }
    return entry, log_path


def append_jsonl(path: Path, entry: dict) -> None:
    ensure_parent(path)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=False) + "\n")


def summarize_log_entries(entries: list[dict], task: str | None) -> dict:
    filtered = [entry for entry in entries if not task or entry.get("task") == task]
    grouped: dict[str, dict[str, list[int]]] = {}

    for entry in filtered:
        task_name = str(entry.get("task", "unknown"))
        mode = str(entry.get("mode", "unknown"))
        grouped.setdefault(task_name, {}).setdefault(mode, []).append(int(entry.get("token_count", 0)))

    comparisons = []
    for task_name in sorted(grouped):
        broad = grouped[task_name].get("broad", [])
        scoped = grouped[task_name].get("memory-scoped", [])
        broad_avg = round(sum(broad) / len(broad), 2) if broad else None
        scoped_avg = round(sum(scoped) / len(scoped), 2) if scoped else None
        savings = None
        percent = None
        if broad_avg is not None and scoped_avg is not None:
            savings = round(broad_avg - scoped_avg, 2)
            percent = round((savings / broad_avg) * 100.0, 2) if broad_avg else 0.0
        comparisons.append(
            {
                "task": task_name,
                "broad_runs": len(broad),
                "memory_scoped_runs": len(scoped),
                "broad_avg_tokens": broad_avg,
                "memory_scoped_avg_tokens": scoped_avg,
                "avg_savings": savings,
                "avg_percentage_savings": percent,
            }
        )

    return {
        "mode": "summarize-log",
        "generated_at": now_utc(),
        "task_filter": task,
        "comparisons": comparisons,
    }


def load_jsonl(path: Path) -> list[dict]:
    entries: list[dict] = []
    if not path.is_file():
        raise FileNotFoundError(f"Log file not found: {path}")
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        entries.append(json.loads(line))
    return entries


def print_human_compare(payload: dict) -> None:
    print("Static context comparison")
    print(f"  tokenizer: {payload['tokenizer']['strategy']}")
    print(f"  baseline tokens: {payload['baseline']['token_count']}")
    print(f"  optimized tokens: {payload['optimized']['token_count']}")
    print(f"  absolute savings: {payload['absolute_savings']}")
    print(f"  percentage savings: {payload['percentage_savings']}%")
    print(f"  note: {payload['tokenizer']['note']}")


def print_human_log(entry: dict, log_path: Path) -> None:
    print("Task-run token log entry")
    print(f"  task: {entry['task']}")
    print(f"  mode: {entry['mode']}")
    print(f"  token count: {entry['token_count']}")
    print(f"  file count: {entry['file_count']}")
    print(f"  log file: {log_path}")


def print_human_summary(payload: dict, log_path: Path) -> None:
    print("Task-run log summary")
    print(f"  log file: {log_path}")
    if not payload["comparisons"]:
        print("  no comparable entries found")
        return
    for item in payload["comparisons"]:
        print(
            "  {task}: broad={broad} memory-scoped={scoped} savings={savings} ({percent}%)".format(
                task=item["task"],
                broad=item["broad_avg_tokens"],
                scoped=item["memory_scoped_avg_tokens"],
                savings=item["avg_savings"],
                percent=item["avg_percentage_savings"],
            )
        )


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="Print JSON instead of human-readable text.")

    parser = argparse.ArgumentParser(
        description="Measure repo-controlled context savings from scoped project memory."
    )
    parser.add_argument(
        "--json",
        dest="json_global",
        action="store_true",
        help="Print JSON instead of human-readable text.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    compare = subparsers.add_parser(
        "compare",
        parents=[common],
        help="Compare a broad baseline context set against an optimized memory-scoped set.",
    )
    compare.add_argument("--project", default=".", help="Project repo root used for relative output paths.")
    compare.add_argument("--baseline", nargs="*", help="Baseline context paths.")
    compare.add_argument("--baseline-list", help="Text file containing one baseline path per line.")
    compare.add_argument("--optimized", nargs="*", help="Optimized context paths.")
    compare.add_argument("--optimized-list", help="Text file containing one optimized path per line.")
    compare.add_argument(
        "--tokenizer",
        default="auto",
        choices=["auto", "tiktoken-cl100k", "chars4-estimate"],
        help="Tokenizer strategy. auto prefers tiktoken cl100k_base, otherwise falls back to a chars/4 estimate.",
    )
    compare.add_argument("--report-file", help="Optional JSON report path.")

    log_run = subparsers.add_parser(
        "log-run",
        parents=[common],
        help="Append a file-based token estimate entry for a task run.",
    )
    log_run.add_argument("--project", default=".", help="Project repo root.")
    log_run.add_argument("--task", required=True, help="Task label used later for comparison.")
    log_run.add_argument(
        "--mode",
        required=True,
        choices=["broad", "memory-scoped"],
        help="Whether the task used broad or memory-scoped context.",
    )
    log_run.add_argument("--context", nargs="*", help="Context file or directory paths.")
    log_run.add_argument("--context-list", help="Text file containing one context path per line.")
    log_run.add_argument(
        "--tokenizer",
        default="auto",
        choices=["auto", "tiktoken-cl100k", "chars4-estimate"],
        help="Tokenizer strategy.",
    )
    log_run.add_argument("--notes", help="Optional note saved with the log entry.")
    log_run.add_argument(
        "--log-file",
        help="Optional JSONL log path. Defaults to agent-knowledge/Outputs/token-measurements/task-run-log.jsonl when available.",
    )

    summarize = subparsers.add_parser(
        "summarize-log",
        parents=[common],
        help="Summarize logged broad vs memory-scoped runs by task.",
    )
    summarize.add_argument("--project", default=".", help="Project repo root.")
    summarize.add_argument("--task", help="Optional task filter.")
    summarize.add_argument(
        "--log-file",
        help="Optional JSONL log path. Defaults to agent-knowledge/Outputs/token-measurements/task-run-log.jsonl when available.",
    )
    summarize.add_argument("--report-file", help="Optional JSON report path.")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    args.json = bool(getattr(args, "json", False) or getattr(args, "json_global", False))

    try:
        if args.command == "compare":
            counter = TokenCounter(args.tokenizer)
            payload = build_compare_payload(args, counter)
            write_output(args.report_file, payload)
            if args.json:
                print(json_dump(payload))
            else:
                print_human_compare(payload)
            return 0

        if args.command == "log-run":
            counter = TokenCounter(args.tokenizer)
            entry, log_path = build_log_entry(args, counter)
            append_jsonl(log_path, entry)
            if args.json:
                print(json_dump({"mode": "log-run", "log_file": str(log_path), "entry": entry}))
            else:
                print_human_log(entry, log_path)
            return 0

        if args.command == "summarize-log":
            log_path = (
                Path(args.log_file).expanduser()
                if args.log_file
                else resolve_measurement_dir(args.project) / "task-run-log.jsonl"
            )
            payload = summarize_log_entries(load_jsonl(log_path), args.task)
            payload["log_file"] = str(log_path)
            write_output(args.report_file, payload)
            if args.json:
                print(json_dump(payload))
            else:
                print_human_summary(payload, log_path)
            return 0

        parser.error("Unknown command.")
        return 2
    except Exception as exc:  # pragma: no cover - CLI error path
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
