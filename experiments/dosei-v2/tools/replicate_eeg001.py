"""Replay the already-open EEG-001 evaluation in a separate local directory."""

import argparse
import json
from pathlib import Path, PureWindowsPath
import sys


EXPERIMENT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXPERIMENT))

from ocon9000.__main__ import build, digest, freeze, load_manifest, verify_build
from ocon9000.dose import RAW_MD5, METADATA_MD5, _verify
from ocon9000.experiment import add_band_deltas
from ocon9000.models import compare_variant, falsify, run_baseline
from ocon9000.report import plot
from ocon9000.trajectory import describe


FILES = (
    "features.csv", "events.csv", "condition_profiles.json", "qc_summary.json", "metrics.json",
    "holdout_features.csv", "holdout_events.csv", "holdout_condition_profiles.json",
    "holdout_qc_summary.json", "holdout_metrics.json",
    "falsification.json", "trajectory.json", "exploratory_candidates.json", "variant_features.csv",
    "variant_metrics.json", "average_precision.svg",
)
PUBLISHED = ("metrics.json", "holdout_metrics.json", "qc_summary.json", "holdout_qc_summary.json",
             "candidate.json", "build_fingerprints.json", "holdout_release.json", "falsification.json",
             "trajectory.json", "variant_metrics.json", "average_precision.svg")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def replicate(archive, original, replay, output):
    if original == replay or original in replay.parents or replay in original.parents or original in output.parents:
        raise ValueError("Keep replay files and the public report separate from the original run")
    if (output.suffix != ".json" or archive.parent in output.parents or replay in output.parents
            or archive.parent in replay.parents):
        raise ValueError("Write the public JSON report outside the source-data and replay directories")
    manifest = load_manifest(original)
    candidate = read(original / "candidate.json")
    if candidate["accepted_variant"]:
        raise ValueError("Expected the original EEG-001 decision to reject H01")
    source_matches = all(digest(EXPERIMENT.joinpath(*PureWindowsPath(name).parts)) == expected
                         for name, expected in candidate["sources"].items())
    if not source_matches:
        raise ValueError("Replay source files differ from the frozen EEG-001 candidate")
    verify_build(original)
    _verify(archive, RAW_MD5, "raw")
    _verify(archive.with_name("metadata.zip"), METADATA_MD5, "metadata")
    published = EXPERIMENT / "runs/dosei-v2"
    published_manifest = read(published / "manifest.public.json")
    group_counts = {name: len(ids) for name, ids in manifest["groups"].items()}
    checks = {
        "raw_and_metadata_match_published_md5": True,
        "archive_matches_original_manifest": digest(archive) == manifest["archive_sha256"],
        "original_manifest_matches_published_fingerprint": (
            digest(original / "manifest.json") == published_manifest["original_manifest_sha256"]),
        "published_group_counts_match": group_counts == published_manifest["group_counts"],
        "original_public_artifacts_match": all(digest(original / name) == digest(published / name) for name in PUBLISHED),
        "original_release_matches_candidate": (
            read(original / "holdout_release.json")["candidate_sha256"] == digest(original / "candidate.json")),
        "original_development_matches_candidate": all(
            digest(original / name) == expected for name, expected in candidate["development"].items()),
        "frozen_source_matches": source_matches,
    }
    if not all(checks.values()):
        raise ValueError("EEG-001 provenance check failed: " + ", ".join(k for k, v in checks.items() if not v))
    before = {name: digest(original / name) for name in FILES}
    if not replay.exists():
        freeze(archive, replay)
    new_manifest = load_manifest(replay)
    checks["replay_manifest_matches_except_timestamp"] = (
        {k: v for k, v in new_manifest.items() if k != "frozen_at_utc"}
        == {k: v for k, v in manifest.items() if k != "frozen_at_utc"}
    )
    if not checks["replay_manifest_matches_except_timestamp"]:
        raise ValueError("Replay changed a frozen input, split, or dependency version")
    if not (replay / "features.csv").exists():
        build(archive, replay)
    verify_build(replay)
    if not (replay / "holdout_features.csv").exists():
        build(archive, replay, final=True)
    if not (replay / "metrics.json").exists():
        run_baseline(replay / "features.csv", replay)
    if not (replay / "holdout_metrics.json").exists():
        run_baseline(replay / "features.csv", replay, final_path=replay / "holdout_features.csv")
    if not (replay / "falsification.json").exists():
        falsify(replay / "features.csv", replay)
    if not (replay / "trajectory.json").exists():
        describe(replay)
    if not (replay / "variant_metrics.json").exists():
        add_band_deltas(replay / "features.csv", replay / "variant_features.csv")
        compare_variant(replay / "features.csv", replay / "variant_features.csv", replay)
    if not (replay / "average_precision.svg").exists():
        plot(replay)
    checks["original_run_unchanged"] = all(digest(original / name) == value for name, value in before.items())
    matches = {name: digest(replay / name) == value for name, value in before.items()}
    aggregate_values_match = {name: read(original / name) == read(replay / name) for name in PUBLISHED
                              if name in matches and name.endswith(".json")}
    development = read(replay / "metrics.json")
    holdout = read(replay / "holdout_metrics.json")
    report = {
        "status": "REPLICATION",
        "independent_confirmation": False,
        "group_unit": "recording",
        "group_counts": group_counts,
        "provenance_checks": checks,
        "byte_matches": matches,
        "aggregate_values_match": aggregate_values_match,
        "matched": all(checks.values()) and all(matches.values()),
        "development_qc": read(replay / "qc_summary.json"),
        "former_holdout_qc": read(replay / "holdout_qc_summary.json"),
        "development": {key: development[key] for key in ("cohort", "primary_comparison")},
        "former_holdout": {key: holdout[key] for key in ("cohort", "models", "primary_comparison")},
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    pending = output.with_suffix(".json.tmp")
    pending.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    pending.replace(output)
    return report["matched"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("archive", "original", "replay", "output"):
        parser.add_argument(name, type=lambda path: Path(path).resolve())
    args = parser.parse_args()
    try:
        matched = replicate(args.archive, args.original, args.replay, args.output)
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"Replication failed: {exc}\n")
    print(f"EEG-001 replication: {'matched' if matched else 'mismatch'}")
    raise SystemExit(0 if matched else 1)
