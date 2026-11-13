"""Test whether duplicate rows can be merged without guessing structured values."""

import argparse
from collections import Counter
import csv
from io import TextIOWrapper
from itertools import groupby
import json
from pathlib import Path
import sys
from zipfile import ZIP_DEFLATED, ZipFile


EXPERIMENT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXPERIMENT))

from ocon9000.__main__ import digest, load_manifest, save_json
from ocon9000.dose import EVENT_COLUMNS, _members, _schema, blocks, metadata
from ocon9000.features import build_record


def merge_rows(left, right, protected):
    merged = []
    masked = []
    for index, (a, b) in enumerate(zip(left, right)):
        if a and b and a != b:
            if index in protected:
                raise ValueError("Duplicate timestamp contains competing structured EEG or event values")
            masked.append(index)
            merged.append("")
        else:
            merged.append(a or b)
    return merged, masked


def audit(archive, original, local, output):
    if (original in local.parents or local == original or original in output.parents
            or archive.parent in local.parents or local == archive.parent
            or archive.parent in output.parents or local in output.parents or output.suffix != ".json"):
        raise ValueError("Use a new private run directory and a separate public JSON output")
    frozen = load_manifest(original)
    if digest(archive) != frozen["archive_sha256"]:
        raise ValueError("Source archive differs from the frozen release")
    failed = set()
    for name in ("condition_profiles.json", "holdout_condition_profiles.json"):
        for item in json.loads((original / name).read_text(encoding="utf-8")):
            if any("time grid gap, duplicate or reversal" in reason for reason in item["reasons"]):
                failed.add(item["record_id"])
    if not failed:
        raise ValueError("No original time-grid exclusions to audit")

    expected = metadata(archive.with_name("metadata.zip"), failed)
    local.mkdir(parents=True, exist_ok=False)
    recovered = local / "recovered.zip"
    totals = Counter()
    expected_events = Counter()
    provenance = []
    with ZipFile(archive) as source, ZipFile(recovered, "w", compression=ZIP_DEFLATED) as destination:
        members = _members(source)
        for record in sorted(failed):
            member = members[record]
            with (TextIOWrapper(source.open(member), encoding="utf-8-sig", newline="") as raw,
                  TextIOWrapper(destination.open(member.filename, "w"), encoding="utf-8", newline="") as clean):
                reader = csv.reader(raw, strict=True)
                header = next(reader)
                writer = csv.writer(clean)
                writer.writerow(header)
                columns, eeg = _schema(header)
                time = columns["Time"]
                event_fields = {name: columns[name] for name in EVENT_COLUMNS if name in columns}
                protected = {time, *event_fields.values(), *(index for index, _ in eeg)}
                for timestamp, same_time in groupby(reader, key=lambda row: row[time]):
                    rows = list(same_time)
                    if any(len(row) != len(header) for row in rows) or len(rows) > 2:
                        raise ValueError("Unexpected row shape or multiplicity at one timestamp")
                    row = rows[0]
                    if len(rows) == 2:
                        row, masked = merge_rows(*rows, protected)
                        totals["duplicate_pairs"] += 1
                        event = columns.get("EVENT")
                        totals["conflicting_free_text_event_values_archived"] += int(event in masked)
                        totals["conflicting_auxiliary_values_masked"] += sum(index != event for index in masked)
                        totals["complementary_event_fields_merged"] += sum(
                            bool(rows[0][index]) != bool(rows[1][index]) for index in event_fields.values())
                        provenance.append({"record_id": record, "timestamp": timestamp,
                                           "source_event_strings": [item[event] for item in rows] if event is not None else []})
                    for name, index in event_fields.items():
                        if row[index]:
                            event_type = {0.0: "LOC", 1.0: "ROC"}[float(row[index])] if name == "SOC" else name
                            expected_events[event_type] += 1
                    writer.writerow(row)
    save_json(local / "duplicate_provenance.json", provenance)

    found = Counter()
    window_qc = Counter()
    for record in sorted(failed):
        _, events, qc, _ = build_record(blocks(recovered, record))
        found.update(item["event_type"] for item in events)
        window_qc.update(qc)
    source_unchanged = digest(archive) == frozen["archive_sha256"]
    if found != expected_events or not source_unchanged:
        raise ValueError("Recovery did not preserve structured event inventory or archive integrity")
    published_events = {"SOC": sum(item["SOC_trans"] for item in expected.values()),
                        "MOAAS": sum(item["MOAAS_sum"] for item in expected.values())}
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "status": "AUDIT", "records_recovered": len(failed), **dict(totals),
        "recovered_4ms_grid_validated": True,
        "competing_structured_values": False,
        "structured_event_inventory_preserved": True,
        "source_archive_unchanged": source_unchanged,
        "clinical_counts_match_published_metadata": (
            published_events == {"SOC": found["LOC"] + found["ROC"], "MOAAS": found["MOAAS"]}),
        "clinical_events": {"LOC": found["LOC"], "ROC": found["ROC"], "MOAAS": found["MOAAS"]},
        "window_qc": dict(window_qc), "used_in_models": False,
        "clinical_labels_independently_verified": False,
    }
    pending = output.with_suffix(".json.tmp")
    pending.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    pending.replace(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("archive", "original", "local", "output"):
        parser.add_argument(name, type=lambda path: Path(path).resolve())
    args = parser.parse_args()
    try:
        audit(args.archive, args.original, args.local, args.output)
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"Duplicate audit failed: {exc}\n")
