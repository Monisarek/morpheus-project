"""Read logs without returning raw lines, stack frames, or secrets."""
import argparse
import re
from pathlib import Path

PATTERNS = {
    "python_traceback": re.compile(r"Traceback \(most recent call last\)", re.I),
    "error": re.compile(r"\b(error|exception|failed|fatal)\b", re.I),
    "warning": re.compile(r"\bwarn(?:ing)?\b", re.I),
    "quota": re.compile(r"\b(quota|rate.limit|429|resource.exhausted)\b", re.I),
    "timeout": re.compile(r"\b(timeout|timed.out)\b", re.I),
    "oom": re.compile(r"\b(out.of.memory|memoryerror|cuda out of memory|oom)\b", re.I),
}


def add_arguments(parser: argparse.ArgumentParser, operation: str):
    parser.add_argument("--input", required=True)
    parser.add_argument("--max-lines", type=int, default=1_000_000)


def execute(args, operation):
    path = Path(args.input).expanduser().resolve(strict=True)
    if not path.is_file():
        raise ValueError("input_is_not_file")
    if not 1 <= args.max_lines <= 10_000_000:
        raise ValueError("max_lines_out_of_range")
    summary = {key: {"count": 0, "first_line": None, "last_line": None} for key in PATTERNS}
    lines = 0
    complete = True
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for i, line in enumerate(fh, 1):
            if i > args.max_lines:
                complete = False
                break
            lines = i
            for key, pattern in PATTERNS.items():
                if pattern.search(line):
                    item = summary[key]
                    item["count"] += 1
                    item["last_line"] = i
                    if item["first_line"] is None:
                        item["first_line"] = i
    return {"status": "ok" if complete else "partial",
            "summary": f"Scanned {lines} lines; errors={summary['error']['count']}, quotas={summary['quota']['count']}; complete={complete}",
            "lines_scanned": lines, "scan_complete": complete, "indicators": summary,
            "note": "No log message text, token, path, or stack frame emitted"}
