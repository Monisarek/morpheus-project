"""Read and verify the versioned public hypothesis ledger."""

from hashlib import sha256
import json
from pathlib import Path
import re

from ..paths import local_path


ROOT = Path(__file__).resolve().parents[2]
ID = re.compile(r"[a-z][a-z0-9-]{0,49}")


def json_digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def read(root, folder, name, suffix):
    if not isinstance(name, str) or not ID.fullmatch(name):
        raise ValueError("invalid_registry_id")
    path = local_path(root / "lab" / folder / (name + suffix))
    if not path.is_file() or path.stat().st_size > 131072:
        raise ValueError("invalid_registry_file")
    return path.read_bytes()


def inventory(root=ROOT):
    ledger = local_path(root / "lab/registry.jsonl")
    if not ledger.is_file() or ledger.stat().st_size > 131072:
        raise ValueError("invalid_registry_file")
    records = {}
    protocols = set()
    for line in ledger.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        hypothesis, version = row["hypothesis_id"], row["version"]
        if (not isinstance(hypothesis, str) or not ID.fullmatch(hypothesis)
                or type(version) is not int or version < 1):
            raise ValueError("invalid_hypothesis_version")
        key = hypothesis, version
        kind = row["kind"]
        if kind == "protocol":
            if key in records or (version > 1 and (hypothesis, version - 1) not in records):
                raise ValueError("invalid_protocol_history")
            protocol_id = row["protocol"]
            if protocol_id in protocols:
                raise ValueError("protocol_already_registered")
            protocol = json.loads(read(root, "protocols", protocol_id, ".json"))
            if (json_digest(protocol) != row["sha256"] or protocol["id"] != protocol_id
                    or protocol["scope"] not in ("public_nonclinical", "synthetic")):
                raise ValueError("protocol_integrity_failed")
            if "fixture" in row:
                fixture = read(root, "fixtures", row["fixture"], ".csv")
                if sha256(fixture).hexdigest() != protocol["source"]["sha256"]:
                    raise ValueError("source_integrity_failed")
            records[key] = {"hypothesis_id": hypothesis, "version": version, "protocol": protocol_id,
                            "protocol_sha256": row["sha256"], "question": protocol["hypothesis"],
                            "result": None, "review": "AWAITING_LYRA"}
            protocols.add(protocol_id)
        elif kind == "result":
            entry = records[key]
            if entry["result"] is not None:
                raise ValueError("result_already_registered")
            evidence = json.loads(read(root, "evidence", entry["protocol"], ".json"))
            if json_digest(evidence) != row["sha256"] or evidence["id"] != entry["protocol"]:
                raise ValueError("result_integrity_failed")
            entry.update(result=evidence["result"], result_sha256=row["sha256"])
        elif kind == "review":
            entry = records[key]
            link = row["evidence"]
            if (entry["result"] is None or entry["review"] != "AWAITING_LYRA"
                    or row["status"] != "LYRA_INTERNAL_REVIEW"
                    or not isinstance(link, str) or not re.fullmatch(
                        r"https://github\.com/Monisarek/morpheus-project/pull/[1-9][0-9]*(?:#[a-zA-Z0-9_-]+)?", link
                    )):
                raise ValueError("invalid_review_record")
            entry.update(review=row["status"], review_evidence=link)
        else:
            raise ValueError("unknown_registry_record")
    if not records:
        raise ValueError("empty_registry")
    return list(records.values())


def add_arguments(parser, operation):
    parser.add_argument("--query", default="")


def execute(args, operation):
    if len(args.query) > 100:
        raise ValueError("registry_query_too_long")
    try:
        entries = inventory()
    except (OSError, KeyError, TypeError, ValueError):
        raise ValueError("registry_verification_failed") from None
    query = args.query.casefold()
    matches = [entry for entry in entries if query in " ".join(
        (entry["hypothesis_id"], entry["protocol"], entry["question"])
    ).casefold()]
    return {"status": "ok" if len(matches) <= 20 else "partial",
            "summary": f"{len(matches)} matches; {len(entries)} versions verified", "entries": matches[:20]}
