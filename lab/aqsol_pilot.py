"""Prepare and run the one approved AqSolDB cycle on the existing LAB checkpoint."""

import argparse
from collections import Counter
import csv
from hashlib import md5, sha256
from importlib.metadata import version
import io
import json
from math import isfinite
from pathlib import Path
from statistics import mean
import signal
import sys

import lab

ROOT = Path(__file__).resolve().parent
TASK = "aqsol-solubility-v1"
PROTOCOL = ROOT / "protocols" / (TASK + ".json")
FREEZE = ROOT / "evidence/aqsol-v1-freeze.json"
ADMISSION = ROOT / "evidence/aqsol-v1-admission.json"


def digest(data):
    return sha256(lab.encode(data).encode()).hexdigest()


def environment():
    requirements = dict(line.split("==") for line in
                        (ROOT / "aqsol-requirements.txt").read_text(encoding="ascii").splitlines())
    installed = {package: version(package) for package in requirements}
    if installed != requirements or sys.version_info[:2] != (3, 12):
        raise ValueError("aqsol_environment_changed")
    return {"python": sys.version.split()[0], "packages": installed}


def fingerprint():
    return {name: sha256((ROOT / name).read_text(encoding="utf-8").encode()).hexdigest()
            for name in ("aqsol_pilot.py", "aqsol_model.py", "lab.py")}


def source_rows(path, protocol):
    source = protocol["source"]
    raw = path.read_bytes()
    if (protocol["id"] != TASK or protocol["scope"] != "public_nonclinical"
            or source["file_id"] != 3407241 or source["version"] != "1.0"
            or source["license"] != "CC0-1.0" or len(raw) != source["original_bytes"]
            or md5(raw).hexdigest() != source["publisher_md5"] or sha256(raw).hexdigest() != source["sha256"]):
        raise ValueError("aqsol_source_integrity_failed")
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
    header = reader.fieldnames or []
    rows = list(reader)
    if (len(rows) != 9982 or len(header) != 26 or len(set(header)) != 26
            or not {"SMILES", "Solubility"} <= set(header)
            or any(None in row or None in row.values() for row in rows)):
        raise ValueError("aqsol_source_schema_failed")
    return rows


def descriptor_record(smiles):
    from rdkit import Chem, rdBase
    from rdkit.Chem import Crippen, Descriptors, Lipinski, rdMolDescriptors
    from rdkit.Chem.Scaffolds import MurckoScaffold

    params = Chem.SmilesParserParams()
    params.parseName = False
    params.allowCXSMILES = False
    with rdBase.BlockLogs():
        mol = Chem.MolFromSmiles(smiles, params)
    if not mol:
        return "invalid_smiles", None
    if len(Chem.GetMolFrags(mol)) != 1:
        return "multiple_fragments", None
    rings = Lipinski.RingCount(mol)
    if not rings:
        return "acyclic", None
    if any(stereo.specified != Chem.StereoSpecified.Specified for stereo in Chem.FindPotentialStereo(mol)):
        return "unresolved_stereochemistry", None
    identity = Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)
    scaffold = MurckoScaffold.MurckoScaffoldSmiles(mol=mol, includeChirality=False)
    features = [Descriptors.MolWt(mol), Crippen.MolLogP(mol), rdMolDescriptors.CalcTPSA(mol),
                Lipinski.NumHDonors(mol), Lipinski.NumHAcceptors(mol), Lipinski.NumRotatableBonds(mol),
                rings, mol.GetNumHeavyAtoms(), rdMolDescriptors.CalcFractionCSP3(mol)]
    if not identity or not scaffold or not all(isfinite(x) for x in features):
        raise ValueError("aqsol_descriptor_integrity_failed")
    return None, [identity, scaffold, features]


def eligible(rows):
    excluded = Counter()
    retained = []
    identities = Counter()
    for row in rows:
        reason, record = descriptor_record(row["SMILES"])
        if reason:
            excluded[reason] += 1
            continue
        identities[record[0]] += 1
        try:
            label = float(row["Solubility"])
        except ValueError:
            label = float("nan")
        if not isfinite(label):
            excluded["nonfinite_label"] += 1
            continue
        retained.append(record + [label])
    unique = [record for record in retained if identities[record[0]] == 1]
    excluded["repeated_identity"] = len(retained) - len(unique)
    return unique, dict(excluded)


def split(records):
    from sklearn.model_selection import GroupShuffleSplit

    groups = [row[1] for row in records]
    if len(records) < 1500 or len(set(groups)) < 100:
        raise ValueError(f"aqsol_eligibility_minimum_failed: rows={len(records)}, groups={len(set(groups))}")
    train_idx, test_idx = next(GroupShuffleSplit(n_splits=1, test_size=0.20, random_state=20261109)
                               .split(records, groups=groups))
    train, test = [records[i] for i in train_idx], [records[i] for i in test_idx]
    return {"train": train, "test": test}


def partition_facts(partition):
    train, test = partition["train"], partition["test"]
    train_ids, test_ids = {r[0] for r in train}, {r[0] for r in test}
    train_groups, test_groups = {r[1] for r in train}, {r[1] for r in test}
    total = len(train) + len(test)
    ratio = len(test) / total if total else 0
    if (total < 1500 or len(train_groups | test_groups) < 100 or not 0.15 <= ratio <= 0.25
            or train_ids & test_ids or train_groups & test_groups
            or len(train_ids) != len(train) or len(test_ids) != len(test)):
        raise ValueError(f"aqsol_frozen_split_gate_failed: train_rows={len(train)}, test_rows={len(test)}, "
                         f"test_fraction={ratio:.6f}, groups={len(train_groups | test_groups)}")
    return {"train_rows": len(train), "test_rows": len(test), "test_fraction": ratio,
            "train_groups": len(train_groups), "test_groups": len(test_groups),
            "scaffold_overlap": 0, "identity_overlap": 0,
            "membership_sha256": digest({k: [r[:2] for r in rows] for k, rows in partition.items()})}


def preparation(protocol, original, state):
    records, exclusions = eligible(source_rows(original, protocol))
    partition = split(records)
    facts = partition_facts(partition)
    prepared = state / "prepared.json"
    lab.guard(state)
    packet = {"partition": partition, "exclusions": exclusions}
    with prepared.open("x", encoding="utf-8") as stream:
        stream.write(lab.encode(packet))
    return {"id": TASK, "scope": protocol["scope"], "protocol_sha256": digest(protocol),
            "source_sha256": protocol["source"]["sha256"], "prepared_sha256": digest(packet),
            "split": facts, "excluded": exclusions, "environment": environment(), "code": fingerprint()}


def preflight(protocol, original, state):
    freeze = json.loads(FREEZE.read_bytes())
    packet = json.loads((state / "prepared.json").read_bytes())
    source_rows(original, protocol)
    if (freeze["id"] != TASK or freeze["scope"] != protocol["scope"]
            or freeze["protocol_sha256"] != digest(protocol)
            or freeze["source_sha256"] != protocol["source"]["sha256"]
            or freeze["prepared_sha256"] != digest(packet)
            or freeze["split"] != partition_facts(packet["partition"])
            or freeze["excluded"] != packet["exclusions"]
            or freeze["environment"] != environment() or freeze["code"] != fingerprint()
            or sum(freeze["excluded"].values()) + freeze["split"]["train_rows"]
            + freeze["split"]["test_rows"] != 9982):
        raise ValueError("aqsol_preflight_integrity_failed")
    return freeze, packet["partition"]


def execute(freeze, partition, state):
    from aqsol_model import predict, score

    train, test = partition["train"], partition["test"]
    labels = [row[3] for row in test]

    def verify(predictions):
        result = score(predictions, labels, [row[1] for row in test])
        for key, values in (("baseline_mae", predictions["baseline"]), ("candidate_mae", predictions["candidate"])):
            if abs(result[key] - mean(abs(label - value) for label, value in zip(labels, values))) > 1e-12:
                raise ValueError("aqsol_independent_mae_check_failed")
        return result

    stages = (
        lab.Stage("verify_frozen_inputs", lambda _: freeze["split"]),
        lab.Stage("fit_and_predict", lambda _: predict([r[2] for r in train], [r[3] for r in train], [r[2] for r in test])),
        lab.Stage("verify_heldout_aggregates", verify),
    )
    return lab.run(state / "checkpoint", packet=freeze, stages=stages)


if __name__ == "__main__":
    if hasattr(signal, "alarm"):
        signal.alarm(300)
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("phase", choices=("prepare", "preflight", "run"))
    parser.add_argument("original", type=Path)
    parser.add_argument("state", type=Path)
    args = parser.parse_args()
    protocol = json.loads(PROTOCOL.read_bytes())
    if args.phase == "prepare":
        result = preparation(protocol, args.original, args.state)
    else:
        freeze, partition = preflight(protocol, args.original, args.state)
        gate = {"status": "PASS_CONDITIONAL_PUBLIC_NONCLINICAL", "id": TASK,
                "freeze_sha256": digest(freeze), "authorization": protocol["authorization"]}
        if args.phase == "preflight":
            result = gate | {"split": freeze["split"]}
        else:
            admission = json.loads(ADMISSION.read_bytes())
            if admission.get("public_gate") != gate or admission.get("mr005_synthetic") != "PASS":
                raise ValueError("aqsol_separate_admission_required")
            result = execute(freeze | {"admission_sha256": digest(admission)}, partition, args.state)
    print(json.dumps(result, sort_keys=True, allow_nan=False))
