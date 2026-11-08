"""Frozen offline Iris pilot. No user-supplied data or model calls."""

from collections import Counter
import csv
from hashlib import sha256
import json
from math import comb
from pathlib import Path
import random
import re
import stat
from statistics import mean
from fractions import Fraction


ROOT = Path(__file__).resolve().parent
TASK = "iris-sepal-v1"
SPECIES = ("Iris-setosa", "Iris-versicolor", "Iris-virginica")
FEATURES = {"sepal_width": 1, "petal_length": 2}


def read_source(path):
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode)
            or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
            or info.st_nlink != 1 or info.st_size > 8192):
        raise ValueError("invalid_public_fixture")
    return path.read_bytes()


def read_protocol(root=ROOT):
    protocol = json.loads(read_source(root / "protocols" / (TASK + ".json")))
    source = protocol["source"]
    if (protocol["id"] != TASK or protocol["scope"] != "public_nonclinical"
            or source["doi"] != "10.24432/C56C76" or source["license"] != "CC-BY-4.0"
            or protocol["predictors"] != {"candidate": "sepal_width", "baseline": "petal_length"}
            or protocol["split"]["test_per_species"] != 10):
        raise ValueError("unapproved_pilot_source")
    return protocol


def inputs(root=ROOT):
    protocol = read_protocol(root)
    raw = read_source(root / "fixtures/iris.csv")
    if sha256(raw).hexdigest() != protocol["source"]["sha256"]:
        raise ValueError("public_fixture_integrity")
    rows = []
    for row in csv.reader(raw.decode("ascii").splitlines()):
        if not row:
            continue
        if len(row) != 5 or row[-1] not in SPECIES or any(
            cell == "0.0" or not re.fullmatch(r"[0-9]\.[0-9]", cell) for cell in row[:4]
        ):
            raise ValueError("invalid_iris_row")
        rows.append(([int(cell.replace(".", "")) for cell in row[:4]], row[-1]))
    if Counter(label for _, label in rows) != dict.fromkeys(SPECIES, 50):
        raise ValueError("unexpected_iris_cohort")
    return protocol, rows


def split(protocol, rows):
    seed = protocol["split"]["seed"]
    count = protocol["split"]["test_per_species"]
    test = set()
    for species in SPECIES:
        group = [i for i, (_, label) in enumerate(rows) if label == species]
        ranked = sorted(group, key=lambda i: sha256(f"{seed}:{i}".encode()).digest())
        test.update(ranked[:count])
    return [i for i in range(len(rows)) if i not in test], sorted(test)


def predict(rows, train, test, column, labels):
    centroids = {
        species: mean(Fraction(rows[i][0][column]) for i, label in zip(train, labels) if label == species)
        for species in SPECIES
    }
    return [min(SPECIES, key=lambda species: abs(rows[i][0][column] - centroids[species])) for i in test]


def experiment(protocol, rows, partition):
    train, test = partition
    labels = [rows[i][1] for i in train]
    shuffled = labels.copy()
    random.Random(protocol["negative_control"]["seed"]).shuffle(shuffled)
    candidate = FEATURES[protocol["predictors"]["candidate"]]
    baseline = FEATURES[protocol["predictors"]["baseline"]]
    return {
        "test": test,
        "candidate": predict(rows, train, test, candidate, labels),
        "baseline": predict(rows, train, test, baseline, labels),
        "negative_control": predict(rows, train, test, candidate, shuffled),
    }


def review(protocol, rows, predictions):
    train, test = split(protocol, rows)
    if predictions["test"] != test or len(test) != 30 or set(train) & set(test):
        raise ValueError("invalid_pilot_split")
    truth = [rows[i][1] for i in test]
    correct = {}
    for name in ("candidate", "baseline", "negative_control"):
        values = predictions[name]
        if len(values) != len(test) or set(values) - set(SPECIES):
            raise ValueError("invalid_pilot_predictions")
        correct[name] = [value == expected for value, expected in zip(values, truth)]
    counts = {name: sum(values) for name, values in correct.items()}
    wins = sum(a and not b for a, b in zip(correct["candidate"], correct["baseline"]))
    losses = sum(b and not a for a, b in zip(correct["candidate"], correct["baseline"]))
    if wins - losses != counts["candidate"] - counts["baseline"]:
        raise ValueError("discordant_counts_do_not_reconcile")
    discordant = wins + losses
    pvalue = sum(comb(discordant, k) for k in range(wins, discordant + 1)) / 2**discordant
    gain = (wins - losses) / len(test)
    control_ok = counts["negative_control"] / len(test) <= protocol["negative_control"]["max_accuracy"]
    criterion = protocol["criterion"]
    supported = gain >= criterion["min_gain"] and pvalue <= criterion["max_pvalue"]
    return {
        "id": TASK, "scope": protocol["scope"], "source": protocol["source"],
        "train_rows": len(train), "test_rows": len(test), "correct": counts,
        "candidate_only_correct": wins, "baseline_only_correct": losses,
        "accuracy_gain": gain, "paired_pvalue": pvalue, "negative_control_ok": control_ok,
        "result": ("SUPPORTED_ON_FIXED_SPLIT" if supported else "NOT_SUPPORTED_ON_FIXED_SPLIT")
        if control_ok else "INCONCLUSIVE_CONTROL",
        "scientific_review": "AWAITING_LYRA",
    }
