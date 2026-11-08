"""MR-022 V2 source and split preflight. This entry point has no fit phase."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

import aqsol_pilot as v1

ROOT = Path(__file__).resolve().parent
TASK = "aqsol-solubility-v2"
PREFIX = "MR022-V2|20261109|"
SPLIT = {
    "method": "Single-pass whole-scaffold greedy assignment in SHA-256 byte order, with scaffold as the tie-break. Admit a group only when it strictly reduces distance from the row target and keeps holdout at or below the row cap.",
    "seed": 20261109,
    "hash_prefix": PREFIX,
    "row_target": "floor(0.20*N+0.5)",
    "row_cap": "floor(0.25*N)",
    "minimum_test_fraction": 0.15,
    "maximum_test_fraction": 0.25,
    "minimum_scaffolds_per_partition": 100,
}


def check_protocol(parent, protocol):
    allowed = {"id", "authorization", "split"}
    if (parent["id"] != v1.TASK or protocol["id"] != TASK or protocol["split"] != SPLIT
            or {k: v for k, v in protocol.items() if k not in allowed}
            != {k: v for k, v in parent.items() if k not in allowed}):
        raise ValueError("v2_protocol_changed_outside_split")


def verify_source(metadata, expected):
    release = metadata["data"]
    entry, = release["files"]
    file = entry["dataFile"]
    if ((release["versionNumber"], release["versionMinorNumber"]) != (1, 0)
            or release["versionState"] != "RELEASED"
            or release["license"]["rightsIdentifier"] != expected["license"]
            or expected["license"] != "CC0-1.0" or entry["restricted"] is not False
            or file["id"] != expected["file_id"] or file["persistentId"] != expected["file_doi"]
            or file["originalFileSize"] != expected["original_bytes"]
            or file["originalFileName"] != "curated-solubility-dataset.csv"
            or file["originalFileFormat"] != "text/csv"
            or file["checksum"] != {"type": "MD5", "value": expected["publisher_md5"]}):
        raise ValueError("v2_official_source_metadata_mismatch")


def scaffold_key(scaffold):
    return sha256((PREFIX + scaffold).encode("utf-8")).digest(), scaffold


def row_limits(total):
    return (2 * total + 5) // 10, total // 4


def select_holdout(sizes):
    target, cap = row_limits(sum(sizes.values()))
    selected = set()
    count = 0
    for scaffold in sorted(sizes, key=scaffold_key):
        proposed = count + sizes[scaffold]
        if proposed <= cap and abs(proposed - target) < abs(count - target):
            selected.add(scaffold)
            count = proposed
    return selected


def verify_decisions(sizes, selected):
    target, cap = row_limits(sum(sizes.values()))
    count = 0
    for scaffold in sorted(sizes, key=lambda s: (sha256(f"MR022-V2|20261109|{s}".encode("utf-8")).digest(), s)):
        proposed = count + sizes[scaffold]
        # For a positive increment this inequality is equivalent to strict improvement.
        take = proposed <= cap and proposed + count < 2 * target
        if take != (scaffold in selected):
            raise ValueError("v2_scaffold_decision_mismatch")
        if take:
            count = proposed


def audit_partitions(train, holdout):
    train_ids, test_ids = {r[0] for r in train}, {r[0] for r in holdout}
    train_groups, test_groups = {r[1] for r in train}, {r[1] for r in holdout}
    total, test_count = len(train) + len(holdout), len(holdout)
    if (len(train_ids) != len(train) or len(test_ids) != test_count or train_ids & test_ids
            or train_groups & test_groups or len(train_groups) < 100 or len(test_groups) < 100
            or 20 * test_count < 3 * total or 4 * test_count > total):
        raise ValueError(f"v2_split_blocked: train_rows={len(train)}, holdout_rows={test_count}, "
                         f"train_scaffolds={len(train_groups)}, holdout_scaffolds={len(test_groups)}, "
                         f"identity_overlap={len(train_ids & test_ids)}, scaffold_overlap={len(train_groups & test_groups)}")
    target, cap = row_limits(total)
    return {"train_rows": len(train), "holdout_rows": test_count, "holdout_fraction": test_count / total,
            "train_scaffolds": len(train_groups), "holdout_scaffolds": len(test_groups),
            "identity_overlap": 0, "scaffold_overlap": 0, "target_rows": target, "cap_rows": cap,
            "membership_sha256": v1.digest({"train": train, "holdout": holdout})}


def preflight(original, metadata):
    parent = json.loads(v1.PROTOCOL.read_bytes())
    protocol = json.loads((ROOT / "protocols" / (TASK + ".json")).read_bytes())
    check_protocol(parent, protocol)
    verify_source(json.loads(metadata.read_bytes()), parent["source"])
    runtime = v1.environment()
    records, excluded = v1.eligible(v1.source_rows(original, parent))
    members = [(row[0], row[1]) for row in records]
    sizes = Counter(scaffold for _, scaffold in members)
    old = json.loads((ROOT / "evidence/aqsol-v1-preflight-blocked.json").read_bytes())
    if (len(members) != old["population"]["eligible_rows"]
            or len(sizes) != old["population"]["unique_scaffolds"]
            or sum(excluded.values()) + len(members) != parent["schema"]["rows"]):
        raise ValueError("v2_v1_population_mismatch")
    selected = select_holdout(sizes)
    verify_decisions(sizes, selected)
    train = [row for row in members if row[1] not in selected]
    holdout = [row for row in members if row[1] in selected]
    split = audit_partitions(train, holdout)
    return {
        "id": TASK, "scope": protocol["scope"], "status": "AWAITING_LYRA_GO_RUN",
        "protocol_sha256": v1.digest(protocol), "v1_protocol_sha256": v1.digest(parent),
        "source": {"doi": parent["source"]["doi"], "file_id": parent["source"]["file_id"],
                   "version": parent["source"]["version"], "license": parent["source"]["license"],
                   "original_bytes": parent["source"]["original_bytes"], "publisher_md5_verified": True,
                   "sha256": parent["source"]["sha256"]},
        "population": {"eligible_rows": len(members), "scaffolds": len(sizes), "excluded": excluded,
                       "v1_filter_reused": True, "ordered_population_sha256": v1.digest(members)},
        "split": split, "independent_decision_check": "PASS", "split_inputs": ["canonical_identity", "scaffold"],
        "runtime": runtime, "fit_authorized": False, "fit_started": False,
        "negative_controls_run": False, "holdout_metrics_computed": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("original", type=Path)
    parser.add_argument("metadata", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(preflight(args.original, args.metadata), sort_keys=True, allow_nan=False))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        if isinstance(exc, ValueError) and str(exc).startswith(("v2_", "aqsol_")):
            reason = str(exc)
        else:
            reason = type(exc).__name__
        print(json.dumps({"status": "BLOCKED", "reason": reason, "fit_started": False}))
        raise SystemExit(1) from None
