"""Second fixed public-data cycle on the existing LAB checkpoint runner."""

import csv
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
from random import Random
from statistics import correlation, fmean
import stat
import sys

import lab


ROOT = Path(__file__).resolve().parent
TASK = "wine-color-v1"


def source(root=ROOT):
    protocol = json.loads((root / f"protocols/{TASK}.json").read_bytes())
    path = root / "fixtures/wine.csv"
    info = path.lstat()
    expected = protocol["source"]
    if (protocol["id"] != TASK or protocol["scope"] != "public_nonclinical"
            or expected["doi"] != "10.24432/C5PC7J" or expected["license"] != "CC-BY-4.0"
            or not stat.S_ISREG(info.st_mode) or info.st_size != 10782
            or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
        raise ValueError("wine_source_not_admitted")
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != expected["sha256"]:
        raise ValueError("wine_source_integrity")
    rows = {key: [] for key in ("1", "2", "3")}
    for row in csv.reader(raw.decode("ascii").splitlines()):
        if len(row) != 14 or row[0] not in rows:
            raise ValueError("wine_schema")
        pair = float(row[1]), float(row[10])
        if not all(isfinite(x) and x > 0 for x in pair):
            raise ValueError("wine_measurement")
        rows[row[0]].append(pair)
    if [len(group) for group in rows.values()] != [59, 71, 48]:
        raise ValueError("wine_group_counts")
    return protocol, list(rows.values())


def centered(groups):
    return [
        [[value - fmean(column) for value in column] for column in zip(*group)]
        for group in groups
    ]


def calculate(criterion, groups):
    alcohol = [x for a, _ in groups for x in a]
    intensities = [b for _, b in groups]
    observed = correlation(alcohol, [x for b in intensities for x in b])
    rng = Random(criterion["seed"])
    draws = []
    for _ in range(criterion["permutations"]):
        shuffled = [b.copy() for b in intensities]
        for group in shuffled:
            rng.shuffle(group)
        draws.append(correlation(alcohol, [x for group in shuffled for x in group]))
    return {"observed": observed, "first_control": draws[0],
            "at_least_observed": sum(x >= observed for x in draws), "groups": groups}


def verify(protocol, result):
    criterion = protocol["criterion"]
    n = criterion["permutations"]
    r, control, exceed = result["observed"], result["first_control"], result["at_least_observed"]
    groups = result["groups"]
    xs = [x for a, _ in groups for x in a]
    ys = [y for _, b in groups for y in b]
    independent_r = sum(x * y for x, y in zip(xs, ys)) / (
        sum(x * x for x in xs) * sum(y * y for y in ys)
    )**0.5
    if (not -1 <= control <= 1 or not 0 <= exceed <= n or abs(r - independent_r) > 1e-12):
        raise ValueError("wine_metric_unverified")
    pvalue = (1 + exceed) / (1 + n)
    control_ok = abs(control) <= criterion["max_control_absolute_correlation"]
    supported = r >= criterion["min_correlation"] and pvalue <= criterion["max_pvalue"]
    return {
        "id": TASK, "scope": protocol["scope"], "source": protocol["source"], "rows": len(xs),
        "cultivar_sizes": [len(a) for a, _ in groups], "within_cultivar_correlation": round(r, 10),
        "permutation_pvalue": pvalue, "permutations": n, "negative_control": round(control, 10),
        "negative_control_ok": control_ok,
        "result": ("SUPPORTED_IN_FIXED_DATASET" if supported else "NOT_SUPPORTED_IN_FIXED_DATASET")
        if control_ok else "INCONCLUSIVE_CONTROL",
        "scientific_review": "AWAITING_LYRA",
    }


def run(directory):
    protocol, raw = source()
    directory.parent.mkdir(exist_ok=True)
    lab.guard(directory.parent)
    packet = {"protocol": protocol, "python": sys.version.split()[0],
              "runner": sha256(Path(lab.__file__).read_bytes()).hexdigest(),
              "pilot": sha256(Path(__file__).read_bytes()).hexdigest()}
    stages = (
        lab.Stage("admit_and_center", lambda _: centered(raw)),
        lab.Stage("calculate", lambda data: calculate(protocol["criterion"], data)),
        lab.Stage("verify", lambda result: verify(protocol, result)),
    )
    result = lab.run(directory, packet=packet, stages=stages)
    if result.get("next_command"):
        result["next_command"] = "py lab/wine_pilot.py"
    return result


if __name__ == "__main__":
    try:
        result = run(ROOT / ".state" / TASK)
    except (OSError, ValueError, KeyError, TypeError):
        print('{"status":"BLOCKED","reason":"wine_inputs_or_checkpoint_unverified"}')
        sys.exit(2)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["status"] == "COMPLETED" else 3)
