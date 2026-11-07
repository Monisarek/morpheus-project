"""Reconcile frozen EEG-001 outcomes and publish aggregate EEG-002 QC coverage."""

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
from io import TextIOWrapper
import json
from math import isclose, isfinite
from pathlib import Path, PurePosixPath
from zipfile import ZipFile


SPLITS = ("train", "validation", "holdout")
TRANSITIONS = {"LOC", "ROC"}
OBSERVATIONS = TRANSITIONS | {"MOAAS"}
USABLE = {"PASS", "WARN"}


def rows(path):
    with path.open(newline="", encoding="utf-8-sig") as stream:
        yield from csv.DictReader(stream, strict=True)


def window_outcome(t, duration, clinical):
    horizon = t + 60
    if horizon >= duration:
        return "right_censored", "", []
    observed = [kind for time, kind in clinical if t < time <= horizon]
    if not observed:
        return "no_observation_in_horizon", "", []
    return "eligible", str(int(bool(TRANSITIONS.intersection(observed)))), observed


def clinical_event(row):
    kind = row["event_type"]
    if kind in TRANSITIONS:
        expected = 0 if kind == "LOC" else 1
        if row["label_source"] != "raw/SOC" or float(row["value"]) != expected:
            raise ValueError("Transition direction contradicts source or raw SOC code")
    elif kind == "MOAAS":
        if row["label_source"] != "raw/MOAAS" or float(row["value"]) not in range(1, 6):
            raise ValueError("MOAAS value contradicts source or valid score range")
    return kind in OBSERVATIONS


def tally(counts, kept):
    counts["denominator"] += 1
    counts["kept"] += int(kept)


def duplicate_rows(source):
    reader = csv.reader(source, strict=True)
    header = next(reader)
    clock = header.index("Time")
    counts = Counter()
    differences = Counter()
    nonblank_conflicts = Counter()
    previous = None
    for row in reader:
        if len(row) != len(header):
            raise ValueError("Ragged raw CSV row in duplicate-clock audit")
        if previous is not None and previous[clock] == row[clock]:
            counts["adjacent_duplicate_pairs"] += 1
            if previous == row:
                counts["exact_pairs"] += 1
            else:
                counts["conflicting_pairs"] += 1
                for column, before, after in zip(header, previous, row):
                    if before != after:
                        differences[column] += 1
                        if before.strip() and after.strip():
                            nonblank_conflicts[column] += 1
        previous = row
    return counts, differences, nonblank_conflicts


def inspect_exclusions(archive, expected_sha256, rejected):
    sha256 = hashlib.sha256()
    with archive.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            sha256.update(block)
    if sha256.hexdigest() != expected_sha256:
        raise ValueError("Raw archive does not match the frozen manifest")
    counts = Counter({"records_inspected": 0, "exact_pairs": 0, "conflicting_pairs": 0})
    differing_columns = Counter()
    nonblank_conflicts = Counter()
    found = set()
    with ZipFile(archive) as source:
        for item in source.infolist():
            rec = PurePosixPath(item.filename).stem.replace("_", "-")
            if rec not in rejected or not item.filename.endswith(".csv"):
                continue
            if rec in found:
                raise ValueError("Multiple raw members match a rejected recording")
            found.add(rec)
            with source.open(item) as binary, TextIOWrapper(binary, encoding="utf-8-sig", newline="") as stream:
                record_counts, columns, competing = duplicate_rows(stream)
            counts.update(record_counts)
            counts["records_inspected"] += 1
            counts["records_with_conflicting_pairs"] += int(record_counts["conflicting_pairs"] > 0)
            differing_columns.update(columns)
            nonblank_conflicts.update(competing)
    if found != rejected:
        raise ValueError("Missing rejected raw recording in the archive")
    return {"archive_matches_original": True, **counts, "differing_columns": differing_columns,
            "both_nonblank_differing_columns": nonblank_conflicts,
            "blank_vs_nonblank_columns": differing_columns - nonblank_conflicts,
            "recovery_rule": "Only consider removal of exact adjacent duplicate rows followed by strict clock validation",
            "records_recovered": 0}


def audit(run, archive=None):
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    groups = manifest["groups"]
    if len(set().union(*map(set, groups.values()))) != sum(map(len, groups.values())):
        raise ValueError("A recording appears in multiple groups or more than once")
    record_counts = defaultdict(Counter)
    funnels = defaultdict(Counter)
    causes = defaultdict(Counter)
    causes_by_class = defaultdict(lambda: defaultdict(Counter))
    class_qc = defaultdict(lambda: defaultdict(Counter))
    strata = defaultdict(lambda: defaultdict(Counter))
    sensitivity = defaultdict(lambda: defaultdict(Counter))
    event_coverage = defaultdict(lambda: defaultdict(Counter))
    mismatches = Counter()
    file_order_ok = True
    rejected = set()
    for prefix in ("", "holdout_"):
        profiles = json.loads((run / f"{prefix}condition_profiles.json").read_text(encoding="utf-8"))
        expected = {key: set(groups[key]) for key in (SPLITS[2:] if prefix else SPLITS[:2])}
        allowed = {(split, rec) for split, ids in expected.items() for rec in ids}
        found = {(row["split"], row["record_id"]) for row in profiles}
        if found != allowed or len(found) != len(profiles):
            raise ValueError("Profile groups do not match the frozen split")
        duration = {}
        events = defaultdict(list)
        feature_times = defaultdict(list)
        for profile in profiles:
            split, rec = profile["split"], profile["record_id"]
            if "duration_s" not in profile:
                rejected.add(rec)
                for label in (split, "all"):
                    record_counts[label]["attempted"] += 1
                    record_counts[label]["unparsed"] += 1
                continue
            duration[split, rec] = float(profile["duration_s"])
            for label in (split, "all"):
                record_counts[label]["attempted"] += 1
                record_counts[label]["parsed"] += 1
                record_counts[label]["duration_4ms_ticks"] += round(duration[split, rec] * 250)
        for row in rows(run / f"{prefix}events.csv"):
            key = row["split"], row["record_id"]
            t = float(row["time_s"])
            if key not in duration or not 0 <= t < duration[key] or not isclose(t * 250, round(t * 250), abs_tol=1e-7, rel_tol=0):
                raise ValueError("Invalid event membership or raw clock")
            clinical_event(row)
            kind = row["event_type"]
            value = float(row["value"]) if kind == "Propofol" else None
            if value is not None and (not isfinite(value) or value <= 0):
                raise ValueError("Invalid Propofol amount")
            events[key].append((t, kind, value))
        for series in events.values():
            if any(a[0] > b[0] for a, b in zip(series, series[1:])):
                raise ValueError("Nonmonotonic event export")

        raw_marks = defaultdict(set)
        indexed_marks = defaultdict(set)
        retained_marks = defaultdict(set)
        model_records = defaultdict(set)
        order = []
        for row in rows(run / f"{prefix}features.csv"):
            split, rec = key = row["split"], row["record_id"]
            if key not in duration:
                raise ValueError("Window without parsed recording profile")
            t = float(row["time_s"])
            feature_times[key].append(t)
            order.append((split, rec, t))
            qc = row["qc"]
            if qc not in USABLE | {"FAIL"}:
                raise ValueError("Unexpected QC state")
            reasons = row["reasons"].split(";") if row["reasons"] else []
            e = events[key]
            clinical = [(time, kind) for time, kind, _ in e if kind in OBSERVATIONS]
            eligibility, target, observed = window_outcome(t, duration[key], clinical)
            mismatch = eligibility != row["eligibility"] or target != row["target"]
            mismatches["outcome_or_eligibility"] += int(mismatch)
            past = [(time, value) for time, kind, value in e if time < t and kind == "Propofol"]
            bolus60 = sum(value for time, value in past if t - 60 <= time)
            age = t - past[-1][0] if past else None
            past_agrees = (isclose(float(row["elapsed_s"]), t, abs_tol=1e-8)
                           and isclose(float(row["dose_mg"]), sum(value for _, value in past), abs_tol=1e-8)
                           and isclose(float(row["dose_60s_mg"]), bolus60, abs_tol=1e-8)
                           and (isclose(float(row["dose_age_s"]), age, abs_tol=1e-8)
                                if age is not None and row["dose_age_s"] else age is None and not row["dose_age_s"]))
            mismatches["causal_context"] += int(not past_agrees)
            if (qc == "FAIL" and any(v for k, v in row.items() if k.startswith("eeg_"))
                    or qc in USABLE and not any(v for k, v in row.items() if k.startswith("eeg_"))):
                mismatches["feature_presence_vs_qc"] += 1
            target_key = "positive" if target == "1" else "negative" if target == "0" else "unknown"
            directions = TRANSITIONS.intersection(observed)
            direction = "+".join(sorted(directions)) if directions else target_key
            for label in (split, "all"):
                f = funnels[label]
                f["grid_windows"] += 1
                f["full_horizon"] += int(eligibility != "right_censored")
                f["observed"] += int(eligibility == "eligible")
                f["model"] += int(eligibility == "eligible" and qc in USABLE)
                causes[label].update(f"{qc}:{reason}" for reason in reasons)
                causes_by_class[label][target_key].update(f"{qc}:{reason}" for reason in reasons)
                class_qc[label][target_key][qc] += 1
                if eligibility != "eligible":
                    continue
                if qc in USABLE:
                    model_records[label].add(key)
                for name, value in (("direction", direction), ("recent_bolus", "yes" if bolus60 else "no"),
                                    ("elapsed_minutes", "0_to_5" if t < 300 else "5_to_15" if t < 900 else "15_plus"),
                                    ("past_endoscopy_marker", "yes" if any(time < t and k == "Endoscopy" for time, k, _ in e) else "no")):
                    tally(strata[label][f"{name}/{value}/{target_key}"], qc in USABLE)
                for rule, keep in (
                    ("original_observed_and_pass_or_warn", qc in USABLE),
                    ("pass_only", qc == "PASS"),
                    ("pass_or_only_interpolation_warning", qc == "PASS" or (qc == "WARN" and reasons == ["interpolated_at_most_5pct"])),
                    ("clinical_observation_within_30s_and_pass_or_warn", qc in USABLE and any(t < time <= t + 30 for time, _ in clinical)),
                    ("moaas_within_60s_and_pass_or_warn", qc in USABLE and "MOAAS" in observed),
                ):
                    tally(sensitivity[label][f"{rule}/{target_key}"], keep)
                for time, kind in clinical:
                    if t < time <= t + 60 and kind in TRANSITIONS:
                        indexed_marks[label].add((rec, time, kind))
                        if qc in USABLE:
                            retained_marks[label].add((rec, time, kind))
        for (split, rec), end in duration.items():
            expected_times = list(range(30, int(end) + 1, 15))
            mismatches["record_grid"] += int(feature_times[split, rec] != expected_times)
            for time, kind, _ in events[split, rec]:
                if kind in TRANSITIONS:
                    for label in (split, "all"):
                        raw_marks[label].add((rec, time, kind))
        file_order_ok &= order == sorted(order)
        for label, marks in raw_marks.items():
            for direction in sorted(TRANSITIONS):
                for name, collection in (("raw", marks), ("in_any_observed_horizon", indexed_marks[label]),
                                         ("in_any_retained_horizon", retained_marks[label])):
                    event_coverage[label][direction][name] += sum(mark[2] == direction for mark in collection)
        for label, ids in model_records.items():
            record_counts[label]["contributing_model_windows"] += len(ids)

    report = {"scientific_status": "AUDIT / SENSITIVITY; EEG-001 partitions reused",
            "group_unit": "recording", "score_unit": "window", "person_identity_confirmed": False,
            "records": record_counts, "funnel": funnels, "qc_by_outcome": class_qc,
            "qc_reasons": causes, "outcome_strata": strata, "rule_sensitivity": sensitivity,
            "qc_reasons_by_outcome": causes_by_class,
            "unique_transition_coverage": event_coverage,
            "reconciliation_mismatches": {key: mismatches[key] for key in (
                "outcome_or_eligibility", "causal_context", "feature_presence_vs_qc", "record_grid")},
            "generated_order_matches_model_sort": file_order_ok,
            "scope": {"sensitivity_denominator": "Original observed windows of same class; alternate rules only restrict them",
                      "strata_denominator": "Original observed windows in each stratum",
                      "endoscopy": "Past marker availability is a procedure timing proxy, not sedation phase",
                      "emg_or_motion": "Not measured by these EEG-001 exports",
                      "clinical": "Targets reconciled from normalized raw-event export, not independent clinician relabeling"}}
    if archive is not None:
        report["raw_duplicate_clock_audit"] = inspect_exclusions(archive, manifest["archive_sha256"], rejected)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--archive", type=Path, help="Verified source archive for auditing rejected records")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.run, args.archive)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return int(any(result["reconciliation_mismatches"].values()))


if __name__ == "__main__":
    raise SystemExit(main())
