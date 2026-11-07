"""Compare reproducibility artifacts without displaying hashes or row-level content."""
import argparse
import hashlib

from ..paths import iter_files, local_path


def add_arguments(parser: argparse.ArgumentParser, operation: str):
    parser.add_argument("--left", required=True)
    parser.add_argument("--right", required=True)
    parser.add_argument("--max-files", type=int, default=20000)


def _digest(path):
    d = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            block = f.read(1024 * 1024)
            if not block:
                break
            d.update(block)
    return d.digest()


def _collect(path, limit):
    if path.is_file():
        return {"": path}
    if not path.is_dir():
        raise ValueError("not_file_or_directory")
    items = {}
    for file in iter_files(path):
        items[file.relative_to(path).as_posix()] = file
        if len(items) > limit:
            raise ValueError("too_many_files")
    return items


def execute(args, operation):
    if not 1 <= args.max_files <= 100000:
        raise ValueError("max_files_out_of_range")
    left = _collect(local_path(args.left), args.max_files)
    right = _collect(local_path(args.right), args.max_files)
    lk, rk = set(left), set(right)
    only_left, only_right = lk - rk, rk - lk
    common = lk & rk
    mismatched = 0
    matched = 0
    for k in sorted(common):
        if left[k].stat().st_size != right[k].stat().st_size or _digest(left[k]) != _digest(right[k]):
            mismatched += 1
        else:
            matched += 1
    same = not only_left and not only_right and mismatched == 0
    return {"status": "ok" if same else "failed_check", "summary": "MATCH" if same else "MISMATCH",
            "match": same, "identical_files": matched, "different_files": mismatched,
            "only_left_count": len(only_left), "only_right_count": len(only_right),
            "note": "Hashes and file names are not included; independent scientific replication requires separate computation"}
