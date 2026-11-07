"""Single command entrypoint for discovery and bounded deterministic execution."""
import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path

from . import __version__
from . import registry
from .paths import iter_files, local_path

CACHE_DIR = Path(os.environ.get("MORPHEUS_TOOL_CACHE", ".morpheus/tool_runs"))


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError("invalid_arguments")


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _fingerprint(path, mode):
    path = local_path(path)
    h = hashlib.sha256()
    if path.is_file():
        files = [(".", path)]
    elif path.is_dir():
        files = []
        for file in iter_files(path):
            files.append((file.relative_to(path).as_posix(), file))
            if len(files) > 20000:
                raise ValueError("too_many_input_files_for_cache")
    else:
        raise ValueError("not_file_or_directory")
    for name, file in files:
        stat = file.stat()
        h.update(name.encode("utf-8"))
        h.update(str(stat.st_size).encode("ascii"))
        if mode == "metadata":
            h.update(str(stat.st_mtime_ns).encode("ascii"))
        elif mode == "content":
            with file.open("rb") as fh:
                for block in iter(lambda: fh.read(1024 * 1024), b""):
                    h.update(block)
    h.update(str(path).encode("utf-8"))
    return h.hexdigest()  # internal: never display digest


def _inputs(namespace):
    return [(key, getattr(namespace, key)) for key in ("input", "left", "right") if getattr(namespace, key, None)]


def _safe_write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".report-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(_json(value) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def _run(entry, argv):
    parser = SafeArgumentParser(prog=f"python -m morpheus_tools run {entry['id']}")
    mod = registry.resolve(entry)
    mod.add_arguments(parser, entry["operation"])
    parser.add_argument("--cache-mode", choices=("off", "metadata", "content"), default="off")
    args = parser.parse_args(argv)
    args_values = vars(args).copy()
    cache_mode = args_values.pop("cache_mode")
    if entry.get("network") and cache_mode != "off":
        raise ValueError("network_evidence_cache_reuse_disabled")
    cache_key = None
    root = CACHE_DIR.resolve()
    tool_file = Path(mod.__file__).resolve()
    tool_impl = hashlib.sha256(tool_file.read_bytes()).hexdigest()
    if cache_mode != "off":
        inputs = {name: _fingerprint(val, cache_mode) for name, val in _inputs(args)}
        key_blob = _json({"tool": entry["id"], "version": entry["version"], "implementation": tool_impl,
                          "arguments": args_values, "input_fingerprints": inputs, "mode": cache_mode})
        cache_key = hashlib.sha256(key_blob.encode("utf-8")).hexdigest()
        cache_path = root / f"{entry['id'].replace('.', '-')}-{cache_key}.json"
        if cache_path.exists():
            result = json.loads(cache_path.read_text(encoding="utf-8"))
            print(_short(result, "hit", cache_path, cache_mode))
            return _status_code(result["status"])
    start = time.monotonic()
    result = mod.execute(args, entry["operation"])
    if not isinstance(result, dict) or result.get("status") not in {"ok", "partial", "failed_check"}:
        raise ValueError("invalid_tool_result_contract")
    result.update({"schema_version": 1, "tool": entry["id"], "tool_version": entry["version"],
                   "elapsed_seconds": round(time.monotonic() - start, 3),
                   "provenance": "content_verified" if cache_mode == "content" else
                                 ("metadata_only_not_for_scientific_proof" if cache_mode == "metadata" else "uncached")})
    if cache_key:
        path = cache_path
    else:
        path = root / f"run-{int(time.time() * 1000000)}-{os.getpid()}.json"
    _safe_write(path, result)
    print(_short(result, "miss" if cache_key else "off", path, cache_mode))
    return _status_code(result["status"])


def _short(result, cache, path, mode):
    safe = {"status": result["status"], "tool": result["tool"], "summary": result.get("summary"),
            "cache": cache, "cache_mode": mode, "report_path": str(path), "provenance": result["provenance"]}
    for key in ("rows_scanned", "scan_complete", "empty_subsets", "missing_columns", "match", "different_files", "only_left_count", "only_right_count", "lines_scanned"):
        if key in result:
            safe[key] = result[key]
    out = _json(safe)
    if len(out.encode("utf-8")) > 4000:
        safe = {k: safe[k] for k in ("status", "tool", "summary", "cache", "cache_mode", "report_path", "provenance")}
        out = _json(safe)
    return out


def _status_code(status):
    return {"ok": 0, "failed_check": 2, "partial": 3}[status]


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    p = SafeArgumentParser(prog="python -m morpheus_tools", description="MORPHEUS reusable deterministic tools")
    p.add_argument("command", choices=["list", "find", "describe", "validate", "run", "version"])
    p.add_argument("rest", nargs=argparse.REMAINDER)
    try:
        opt = p.parse_args(argv)
        if opt.command == "version":
            print(__version__)
            return 0
        if opt.command == "validate":
            print(_json({"status": "ok", **registry.validate()}))
            return 0
        tools = registry.inventory()
        if opt.command == "list":
            print(_json([{"id": x["id"], "version": x["version"], "kind": x["kind"], "description": x["description"]} for x in tools]))
            return 0
        if opt.command == "find":
            if not opt.rest:
                raise ValueError("missing_search_query")
            words = " ".join(opt.rest).casefold().split()
            hits = []
            for entry in tools:
                haystack = " ".join([entry["id"], entry["description"], *entry["triggers"]]).casefold()
                if all(word in haystack for word in words):
                    hits.append({"id": entry["id"], "kind": entry["kind"], "description": entry["description"], "example": entry["example"]})
            print(_json(hits[:20]))
            return 0
        if opt.command == "describe":
            if len(opt.rest) != 1:
                raise ValueError("describe_requires_one_id")
            matches = [entry for entry in tools if entry["id"] == opt.rest[0]]
            if not matches:
                raise ValueError("unknown_tool")
            print(_json(matches[0]))
            return 0
        if opt.command == "run":
            if not opt.rest:
                raise ValueError("run_requires_tool_id")
            entry = next((t for t in tools if t["id"] == opt.rest[0]), None)
            if entry is None:
                raise ValueError("unknown_tool")
            if entry["kind"] == "documented_external":
                raise ValueError("documented_external_run_directly_check_help_and_state")
            return _run(entry, opt.rest[1:])
        raise ValueError("unknown_command")
    except Exception as exc:
        error = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        if len(error) > 120 or "xox" in error or "xapp" in error:
            error = "invalid_input_or_execution_error"
        print(_json({"status": "error", "code": error, "help": "Use list / find / describe and check local logs"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
