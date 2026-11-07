"""Bounded, streaming aggregates. Never return row values or sampled records."""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path

SUPPORTED = {".csv", ".tsv", ".jsonl", ".parquet"}


def add_arguments(parser: argparse.ArgumentParser, operation: str):
    parser.add_argument("--input", required=True, help="Local CSV, TSV, JSONL, or Parquet file")
    parser.add_argument("--max-rows", type=int, default=50000, help="Limit exploration scan; partial scans never certify absent subsets")
    if operation == "empty_check":
        parser.add_argument("--require-column", action="append", default=[])
        parser.add_argument("--expect-subset", action="append", default=[], help="literal column=value, repeated")


def _rows(path, max_rows):
    """Return column names, iterable of plain row dictionaries, and scan-completeness indicator."""
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED:
        raise ValueError("unsupported_file_type")
    if suffix in {".csv", ".tsv"}:
        fp = path.open("r", encoding="utf-8-sig", newline="")
        reader = csv.DictReader(fp, delimiter="\t" if suffix == ".tsv" else ",")
        headers = list(reader.fieldnames or [])
        if any(c is None or not c.strip() for c in headers) or len(set(headers)) != len(headers):
            fp.close()
            raise ValueError("invalid_or_duplicate_csv_columns")
        return headers, _bounded(reader, fp, max_rows)
    if suffix == ".jsonl":
        fp = path.open("r", encoding="utf-8-sig")
        return [], _bounded((_parse_line(line) for line in fp if line.strip()), fp, max_rows)
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise ValueError("parquet_requires_pyarrow_optional_dependency") from exc
    parquet = pq.ParquetFile(path)
    headers = parquet.schema_arrow.names
    if len(set(headers)) != len(headers):
        raise ValueError("duplicate_parquet_columns")
    def parquet_rows():
        for batch in parquet.iter_batches(batch_size=1024):
            yield from batch.to_pylist()
    return list(headers), _bounded(parquet_rows(), None, max_rows)


def _parse_line(line):
    try:
        value = json.loads(line)
    except (ValueError, TypeError) as exc:
        raise ValueError("invalid_jsonl_record") from exc
    if not isinstance(value, dict):
        raise ValueError("jsonl_record_is_not_object")
    return value


def _bounded(iterator, fp, limit):
    try:
        for i, row in enumerate(iterator):
            if i == limit:
                yield None  # sentinel: scan NOT complete
                return
            if not isinstance(row, dict):
                raise ValueError("invalid_row")
            yield row
    finally:
        if fp is not None:
            fp.close()


def _is_value(v):
    if v is None:
        return False
    if isinstance(v, float) and v != v:
        return False
    return not (isinstance(v, str) and not v.strip())


def execute(args, operation):
    path = Path(args.input).expanduser().resolve(strict=True)
    if not path.is_file():
        raise ValueError("input_is_not_file")
    if args.max_rows < 1 or args.max_rows > 5_000_000:
        raise ValueError("max_rows_out_of_range")
    headers, iterator = _rows(path, args.max_rows)
    nonempty = Counter()
    rows = 0
    complete = True
    required = list(getattr(args, "require_column", []))
    expected = []
    for item in getattr(args, "expect_subset", []):
        if "=" not in item:
            raise ValueError("expect_subset_requires_column_equals_value")
        col, val = item.split("=", 1)
        if not col.strip():
            raise ValueError("empty_subset_column")
        expected.append((col, val))
    hits = [0] * len(expected)
    for row in iterator:
        if row is None:
            complete = False
            break
        rows += 1
        if len(headers) < 256:
            for col in row.keys():
                if col not in headers:
                    headers.append(col)
            if len(headers) > 256:
                raise ValueError("too_many_columns")
        elif any(k not in headers for k in row):
            raise ValueError("too_many_columns")
        for col, value in row.items():
            if col is None:
                raise ValueError("unstructured_csv_extra_columns")
            if _is_value(value):
                nonempty[col] += 1
        for i, (col, value) in enumerate(expected):
            if str(row.get(col, "")) == value and col in row:
                hits[i] += 1
    schema_complete = complete or path.suffix.lower() != ".jsonl"
    missing_required = sorted(set(required + [x[0] for x in expected]) - set(headers)) if schema_complete else []
    checks = []
    for i, (column, _) in enumerate(expected):
        present = column in headers
        checks.append({"check_id": f"check_{i+1}",
                       "column_present": present if present or schema_complete else None,
                       "matching_rows": hits[i], "empty": hits[i] == 0 if complete else None})
    if operation == "profile":
        by_col = {col: {"nonempty": nonempty[col], "empty": rows - nonempty[col]} for col in headers}
        return {"status": "ok" if complete else "partial",
                "summary": f"Scanned {rows} rows, {len(headers)} columns; complete={complete}",
                "rows_scanned": rows, "scan_complete": complete,
                "column_count": len(headers), "column_presence": by_col,
                "note": "No raw rows or observed values emitted"}
    empty_subsets = [a["check_id"] for a in checks if a["empty"] is True]
    failed = bool(missing_required or empty_subsets or (rows == 0 and complete))
    status = "failed_check" if failed else ("partial" if not complete else "ok")
    return {"status": status,
            "summary": f"Scanned {rows} rows; complete={complete}; empty checks={len(empty_subsets)}; missing columns={len(missing_required)}",
            "rows_scanned": rows, "scan_complete": complete,
            "missing_columns": missing_required, "empty_subsets": empty_subsets,
            "checks": checks, "note": "Check IDs omit potentially identifying subset values"}
