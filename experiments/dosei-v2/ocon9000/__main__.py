"""Command line for versioned DOSE-I research runs."""

import argparse
from collections import Counter
import csv
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
import platform
import sys
from datetime import datetime, timezone
from zipfile import BadZipFile

from .dose import blocks, metadata, profile, recordings


SEED = 9000
DATASET_DOI = "10.5281/zenodo.22145442"
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ARCHIVE = Path("data/dose-i/data.zip")
DUA = "https://zenodo.org/records/22145442/files/Data_Use_Agreement.txt?download=1"


def digest(path):
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def partitions(ids):
    if len(set(ids)) != len(ids) or len(ids) < 5:
        raise ValueError("At least five distinct recording IDs are required")
    ranked = sorted(ids, key=lambda record: hashlib.sha256(f"{SEED}:{record}".encode()).digest())
    n = len(ranked)
    return {"train": sorted(ranked[: n * 3 // 5]),
            "validation": sorted(ranked[n * 3 // 5 : n * 4 // 5]),
            "holdout": sorted(ranked[n * 4 // 5 :])}


def save_json(path, value):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def freeze(archive, run):
    ids = recordings(archive)
    groups = partitions(ids)
    manifest = {"dataset_doi": DATASET_DOI, "dataset_version": 2, "license": "CC-BY-4.0", "dua": DUA,
                "archive_sha256": digest(archive), "seed": SEED, "group_unit": "recording",
                "subject_identity_confirmed": False, "groups": groups,
                "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
                "protocol_sha256": digest(ROOT / "RESEARCH_PROTOCOL.md"), "python": platform.python_version()}
    versions = {}
    for package in ("numpy", "scipy", "scikit-learn", "matplotlib"):
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            versions[package] = None
    manifest["versions"] = versions
    run.mkdir(parents=True, exist_ok=False)
    save_json(run / "manifest.json", manifest)
    return {"run": str(run), "groups": {key: len(ids) for key, ids in groups.items()}}


def load_manifest(run):
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    if manifest["protocol_sha256"] != digest(ROOT / "RESEARCH_PROTOCOL.md"):
        raise ValueError("Research protocol differs from frozen manifest")
    groups = manifest["groups"]
    ids = [record for group in groups.values() for record in group]
    if manifest["dataset_doi"] != DATASET_DOI or manifest["seed"] != SEED or groups != partitions(ids):
        raise ValueError("Invalid or changed split manifest")
    return manifest


def write_csv(path, rows):
    keys = list(dict.fromkeys(key for row in rows for key in row))
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def stage_hashes(run, paths):
    return {name: digest(run / name) for name in paths}


def verify_build(run):
    frozen = json.loads((run / "build_fingerprints.json").read_text(encoding="utf-8"))
    if frozen != stage_hashes(run, ("manifest.json", "features.csv", "events.csv", "qc_summary.json", "condition_profiles.json")):
        raise ValueError("Development files differ from the completed build")


def build(archive, run, *, final=False):
    from .features import build_record

    manifest = load_manifest(run)
    if digest(archive) != manifest["archive_sha256"]:
        raise ValueError("Archive differs from frozen release")
    if manifest["groups"] != partitions(recordings(archive, verify=False)):
        raise ValueError("Frozen groups differ from the verified archive inventory")
    parts = ["holdout"] if final else ["train", "validation"]
    prefix = "holdout_" if final else ""
    if (run / f"{prefix}features.csv").exists():
        raise ValueError("Feature stage already exists. Use a new run directory to repeat it.")
    meta_archive = archive.with_name("metadata.zip")
    allowed_ids = {record for split in parts for record in manifest["groups"][split]}
    source_meta = metadata(meta_archive, allowed_ids) if meta_archive.is_file() else {}
    profiles, windows, annotations = [], [], []
    totals = Counter()
    queue = [(split, record) for split in parts for record in manifest["groups"][split]]
    for i, (split, record_id) in enumerate(queue):
        if i % 20 == 0:
            print(f"Processed {i}/{len(queue)} recordings", file=sys.stderr, flush=True)
        key = {"record_id": record_id, "split": split}
        record_profile = {**profile(record_id), **key}
        try:
            rows, events, qc_counts, duration = build_record(blocks(archive, record_id))
        except (ValueError, OSError, csv.Error, BadZipFile) as exc:
            profiles.append({**record_profile, "qc": "FAIL", "reasons": [str(exc)]})
            totals["failed_records"] += 1
            continue
        event_counts = Counter(e["event_type"] for e in events)
        status = "FAIL" if not rows or qc_counts.get("qc_FAIL", 0) == len(rows) else "PASS"
        if status == "PASS" and (qc_counts.get("qc_WARN") or qc_counts.get("qc_FAIL")):
            status = "WARN"
        doses = [e["time_s"] for e in events if e["event_type"] == "Propofol"]
        reasons = []
        if expected := source_meta.get(record_id):
            if abs(expected["length"] - duration) > 1:
                reasons.append("published_duration_differs")
            if expected["SOC_trans"] != event_counts["LOC"] + event_counts["ROC"]:
                reasons.append("published_transition_count_differs")
            if expected["MOAAS_sum"] != event_counts["MOAAS"]:
                reasons.append("published_assessment_count_differs")
            if expected["residual_errors"]:
                reasons.append("publisher_flagged_record")
        if reasons and status == "PASS":
            status = "WARN"
        record_profile.update(duration_s=duration, qc=status, qc_counts=qc_counts, event_counts=dict(event_counts),
                              first_propofol_s=doses[0] if doses else "UNKNOWN",
                              published_metadata=source_meta.get(record_id, "UNKNOWN"), reasons=reasons)
        profiles.append(record_profile)
        totals.update(qc_counts)
        totals.update({"annotated_transitions": event_counts["LOC"] + event_counts["ROC"],
                       "clinical_scores": event_counts["MOAAS"], "parsed_records": 1,
                       "records_without_usable_signal": int(status == "FAIL")})
        windows.extend({**key, **row} for row in rows)
        annotations.extend({**key, **event} for event in events)
    totals["records_attempted"] = len(profiles)
    totals["record_qc"] = dict(Counter(item["qc"] for item in profiles))
    save_json(run / f"{prefix}qc_summary.json", dict(totals))
    save_json(run / f"{prefix}condition_profiles.json", profiles)
    write_csv(run / f"{prefix}events.csv", annotations)
    if not windows:
        raise ValueError("No windows produced. See QC summary and condition profiles.")
    write_csv(run / f"{prefix}features.csv", windows)
    if not final:
        save_json(run / "build_fingerprints.json", stage_hashes(run, ("manifest.json", "features.csv", "events.csv",
                                                                     "qc_summary.json", "condition_profiles.json")))
    return dict(totals)


def experiment(run):
    from .experiment import HYPOTHESIS_ID, add_band_deltas
    from .models import compare_variant

    if not (run / "metrics.json").exists():
        raise ValueError("Run the baseline before testing a candidate")
    hypotheses = [json.loads(line) for line in (ROOT / "research/hypotheses.jsonl").read_text(encoding="utf-8").splitlines()]
    if not any(item["id"] == HYPOTHESIS_ID and item["origin_run"] == run.name for item in hypotheses):
        raise ValueError("Register the hypothesis for this run before running the experiment")
    base, variant = run / "features.csv", run / "variant_features.csv"
    add_band_deltas(base, variant)
    return compare_variant(base, variant, run)


def candidate_fingerprints(run, accepted):
    sources = [*(ROOT / "ocon9000").glob("*.py"), ROOT / "requirements.txt", ROOT / "research/hypotheses.jsonl",
               ROOT / "research/decisions.jsonl"]
    results = ["build_fingerprints.json", "metrics.json", "falsification.json", "trajectory.json", "variant_metrics.json"]
    if accepted:
        results.append("variant_features.csv")
    return {"sources": {str(path.relative_to(ROOT)): digest(path) for path in sources},
            "development": stage_hashes(run, results)}


def seal(run):
    if (run / "candidate.json").exists():
        raise ValueError("Candidate already sealed")
    decisions = [json.loads(line) for line in (ROOT / "research/decisions.jsonl").read_text(encoding="utf-8").splitlines()]
    decision = next((item for item in decisions if item["id"] == "H01" and item["run"] == run.name), None)
    if decision is None or decision["decision"] not in {"accepted", "rejected"}:
        raise ValueError("A reviewed candidate decision is required before sealing")
    accepted = decision["decision"] == "accepted"
    variant_result = json.loads((run / "variant_metrics.json").read_text(encoding="utf-8"))
    if accepted and not variant_result["accepted"]:
        raise ValueError("The reviewed candidate did not meet the registered acceptance criterion")
    result = {"accepted_variant": accepted, **candidate_fingerprints(run, accepted)}
    save_json(run / "candidate.json", result)
    return {"candidate": str(run / "candidate.json"), "accepted_variant": accepted}


def holdout(archive, run):
    from .experiment import add_band_deltas
    from .models import run_baseline

    if (run / "holdout_release.json").exists():
        raise ValueError("Holdout release already started for this run. Preserve the release log for audit.")
    candidate = json.loads((run / "candidate.json").read_text(encoding="utf-8"))
    accepted = candidate["accepted_variant"]
    if candidate != {"accepted_variant": accepted, **candidate_fingerprints(run, accepted)}:
        raise ValueError("Code or development evidence differs from the sealed candidate")
    if digest(archive) != load_manifest(run)["archive_sha256"]:
        raise ValueError("Archive differs from frozen release")
    if load_manifest(run)["groups"] != partitions(recordings(archive, verify=False)):
        raise ValueError("Frozen groups differ from the verified archive inventory")
    with (run / "holdout_release.json").open("x", encoding="utf-8") as stream:
        json.dump({"released_at_utc": datetime.now(timezone.utc).isoformat(),
                   "candidate_sha256": digest(run / "candidate.json")}, stream, indent=2)
    counts = build(archive, run, final=True)
    development = run / "features.csv"
    final = run / "holdout_features.csv"
    if accepted:
        development = run / "variant_features.csv"
        variant_final = run / "holdout_variant_features.csv"
        add_band_deltas(final, variant_final)
        final = variant_final
    run_baseline(development, run, final_path=final)
    return {"holdout_metrics": str(run / "holdout_metrics.json"), "holdout_qc": counts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("catalog")
    for name in ("inspect", "freeze", "build", "baseline", "trajectory", "falsify", "experiment", "seal", "holdout", "report"):
        command = commands.add_parser(name)
        if name in {"inspect", "freeze", "build", "holdout"}:
            command.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
        if name != "inspect":
            command.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "catalog":
            result = {"dataset_doi": DATASET_DOI, "version": 2, "license": "CC-BY-4.0", "dua": DUA}
        elif args.command == "inspect":
            ids = recordings(args.archive)
            result = {"archive": str(args.archive), "records": len(ids), "group_unit": "recording", "verified": True}
        elif args.command == "freeze":
            result = freeze(args.archive, args.run)
        elif args.command == "build":
            result = build(args.archive, args.run)
        else:
            load_manifest(args.run)
            verify_build(args.run)
            if args.command == "trajectory":
                from .trajectory import describe

                result = describe(args.run)
            elif args.command in {"baseline", "falsify"}:
                from .models import falsify, run_baseline

                analyze = run_baseline if args.command == "baseline" else falsify
                analyze(args.run / "features.csv", args.run)
                file = "metrics.json" if args.command == "baseline" else "falsification.json"
                result = {args.command: str(args.run / file)}
            elif args.command == "experiment":
                result = experiment(args.run)
            elif args.command == "seal":
                result = seal(args.run)
            elif args.command == "report":
                from .report import plot

                result = {"plot": str(plot(args.run))}
            else:
                result = holdout(args.archive, args.run)
    except (OSError, ValueError, BadZipFile, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
