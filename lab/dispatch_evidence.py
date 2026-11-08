"""Export verified aggregate evidence from the existing Dispatcher receipt."""

import argparse
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

from dispatcher_pilot import TASK, approval, safe_file


def export(database, root):
    source = root / "public"
    packet = approval(root, source)
    expected = sha256(json.dumps(packet, sort_keys=True).encode()).hexdigest()
    with closing(sqlite3.connect(database.absolute().as_uri() + "?mode=ro", uri=True)) as db:
        row = db.execute("SELECT approval,state,evidence FROM dispatch_iris_receipt WHERE task=?",
                         (TASK,)).fetchone()
    evidence = safe_file(source / "evidence/iris-sepal-v1.json")
    digest = sha256(evidence).hexdigest()
    if row != (expected, "COMPLETED", digest):
        raise ValueError("dispatcher_evidence_unconfirmed")
    return {"task": TASK, "approval_sha256": expected, "artifact_sha256": digest,
            "artifact": json.loads(evidence)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("queue", type=Path)
    parser.add_argument("approval_dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(export(args.queue, args.approval_dir), sort_keys=True, allow_nan=False))
