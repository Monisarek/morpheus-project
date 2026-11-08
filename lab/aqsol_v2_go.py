"""Run the single approved AqSolDB V2 cycle with an MR-006 checkpoint."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from math import fsum, isclose
import os
from pathlib import Path
import re
import signal
import socket

import aqsol_model
import aqsol_v2 as v2

v1 = v2.v1
lab = v1.lab
ROOT = Path(__file__).resolve().parent
ACCEPTED_PREFLIGHT = "f2abb54df1639bfb052bcb7d84db060edd295fb10e2893dd887e2983723d70b5"
AUTHORIZATION = "https://morpheusresea-9xx8372.slack.com/archives/C0CGMC7NRL0/p1794167395390289"


def checked_inputs(original, metadata, freeze):
    parent = json.loads(v1.PROTOCOL.read_bytes())
    protocol = json.loads((ROOT / "protocols/aqsol-solubility-v2.json").read_bytes())
    accepted = json.loads((ROOT / "evidence/aqsol-v2-preflight.json").read_bytes())
    source = parent["source"]
    v2.check_protocol(parent, protocol)
    v2.verify_source(json.loads(metadata.read_bytes()), source)
    runtime = v1.environment()
    if (not re.fullmatch(r"[a-f0-9]{40}", freeze) or v1.digest(accepted) != ACCEPTED_PREFLIGHT
            or v1.digest(protocol) != accepted["protocol_sha256"]
            or v1.digest(parent) != accepted["v1_protocol_sha256"] or runtime != accepted["runtime"]
            or original.stat().st_size != source["original_bytes"]
            or sha256(original.read_bytes()).hexdigest() != source["sha256"]):
        raise ValueError("aqsol_v2_frozen_input_mismatch")
    packet = {"id": v2.TASK, "execution_freeze": freeze, "authorization": AUTHORIZATION,
              "preflight_sha256": ACCEPTED_PREFLIGHT, "protocol_sha256": accepted["protocol_sha256"],
              "source_sha256": source["sha256"], "runtime": runtime,
              "runner_sha256": sha256(Path(__file__).read_text(encoding="utf-8").encode()).hexdigest()}
    return parent, accepted, packet


def prepare_partition(original, parent, accepted):
    records, excluded = v1.eligible(v1.source_rows(original, parent))
    members = [(row[0], row[1]) for row in records]
    sizes = Counter(scaffold for _, scaffold in members)
    population = {"eligible_rows": len(members), "scaffolds": len(sizes), "excluded": excluded,
                  "v1_filter_reused": True, "ordered_population_sha256": v1.digest(members)}
    selected = v2.select_holdout(sizes)
    v2.verify_decisions(sizes, selected)
    train = [row for row in records if row[1] not in selected]
    holdout = [row for row in records if row[1] in selected]
    split = v2.audit_partitions([tuple(row[:2]) for row in train], [tuple(row[:2]) for row in holdout])
    if population != accepted["population"] or split != accepted["split"]:
        raise ValueError("aqsol_v2_frozen_membership_mismatch")
    return {"train": [row[2:] for row in train], "holdout": [row[1:] for row in holdout]}


def fit(partition):
    train, holdout = partition["train"], partition["holdout"]
    predictions = aqsol_model.predict([r[0] for r in train], [r[1] for r in train], [r[1] for r in holdout])
    return {"predictions": predictions, "labels": [r[2] for r in holdout], "scaffolds": [r[0] for r in holdout]}


def verify(fitted):
    predictions, labels, scaffolds = fitted["predictions"], fitted["labels"], fitted["scaffolds"]
    result = aqsol_model.score(predictions, labels, scaffolds)
    vectors = [predictions["baseline"], predictions["candidate"], *predictions["controls"]]
    actual = [result["baseline_mae"], result["candidate_mae"], *result["control_maes"]]
    expected = [fsum(abs(y - p) for y, p in zip(labels, vector, strict=True)) / len(labels) for vector in vectors]
    if (any(not isclose(a, b, rel_tol=0, abs_tol=1e-12) for a, b in zip(actual, expected, strict=True))
            or result["test_rows"] != len(labels) or result["test_groups"] != len(set(scaffolds))):
        raise ValueError("aqsol_v2_independent_mae_check_failed")
    return result


def cycle(state, packet, prepare):
    stages = (
        lab.Stage("verify_v2_membership", lambda _: prepare()),
        # MR-006 must block a second fit when the first outcome is unknown.
        lab.Stage("fit_and_predict_v2_once", fit, external=True),
        lab.Stage("verify_heldout_v2_aggregate", verify),
    )
    return lab.run(state, packet=packet, stages=stages)


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("original", type=Path)
    parser.add_argument("metadata", type=Path)
    parser.add_argument("state", type=Path)
    parser.add_argument("freeze")
    args = parser.parse_args()
    try:
        if os.name != "posix" or os.getuid() != 65534 or {name for _, name in socket.if_nameindex()} != {"lo"}:
            raise ValueError("aqsol_v2_offline_sandbox_required")
        signal.alarm(300)
        parent, accepted, packet = checked_inputs(args.original, args.metadata, args.freeze)
        result = cycle(args.state, packet, lambda: prepare_partition(args.original, parent, accepted))
        # The default MR-006 resume command targets a different protocol.
        result.pop("next_command", None)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        reason = str(exc) if isinstance(exc, ValueError) and str(exc).startswith("aqsol_v2_") else type(exc).__name__
        result = {"status": "BLOCKED", "reason": reason}
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0 if result["status"] == "COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
