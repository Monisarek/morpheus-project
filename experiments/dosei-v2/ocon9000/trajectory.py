"""Development-only directional analysis of annotated transition windows."""

from bisect import bisect_left, bisect_right
from collections import defaultdict
import csv

import numpy as np

from .__main__ import SEED, save_json


MEASURE = "eeg_1_rel_alpha"
DIRECTIONS = ("LOC", "ROC")


def contrasts(windows, transitions):
    times = [float(row["time_s"]) for row in windows]
    marks = [time for time, _ in transitions]
    result = defaultdict(list)
    for mark, direction in transitions:
        pre_i = bisect_right(times, mark) - 1
        post_i = bisect_left(times, mark + 30)
        if pre_i < 0 or post_i == len(times):
            continue
        pre, post = windows[pre_i], windows[post_i]
        if mark - times[pre_i] > 15 or times[post_i] - mark > 45:
            continue
        if bisect_left(marks, times[post_i]) - bisect_left(marks, times[pre_i] - 30) != 1:
            continue
        if pre["qc"] not in {"PASS", "WARN"} or post["qc"] not in {"PASS", "WARN"}:
            continue
        dose_stratum = "with_intervening_bolus" if float(post["dose_mg"]) > float(pre["dose_mg"]) else "no_intervening_bolus"
        result[direction].append((float(post[MEASURE]) - float(pre[MEASURE]), dose_stratum, mark))
    return result


def summarize(data, rng):
    per_record = [np.mean(values) for values in data if values]
    if not per_record:
        return {"records": 0, "events": 0, "record_mean_delta": None, "ci95": None}
    reps = rng.choice(per_record, size=(1000, len(per_record))).mean(axis=1)
    return {"records": len(per_record), "events": sum(map(len, data)), "record_mean_delta": float(np.mean(per_record)),
            "ci95": np.quantile(reps, (0.025, 0.975)).tolist() if len(per_record) > 1 else None}


def describe(run):
    windows, annotations = defaultdict(list), defaultdict(list)
    for file, add in (("features.csv", windows), ("events.csv", annotations)):
        with (run / file).open(newline="", encoding="utf-8") as stream:
            for row in csv.DictReader(stream):
                if row["split"] == "holdout":
                    raise ValueError("Holdout cannot be used for exploratory trajectory analysis")
                if row["split"] == "validation":
                    add[row["record_id"]].append(row)
    rng = np.random.default_rng(SEED)
    real = {direction: [] for direction in DIRECTIONS}
    shifted = {direction: [] for direction in DIRECTIONS}
    strata = {direction: defaultdict(list) for direction in DIRECTIONS}
    candidates = {direction: [] for direction in DIRECTIONS}
    totals = {direction: 0 for direction in DIRECTIONS}
    for record, rows in windows.items():
        marks = sorted((float(e["time_s"]), e["event_type"]) for e in annotations[record] if e["event_type"] in DIRECTIONS)
        for _, direction in marks:
            totals[direction] += 1
        extent = float(rows[-1]["time_s"])
        if extent <= 180:
            continue
        shift = rng.uniform(60, extent - 60)
        observed = contrasts(rows, marks)
        placebo = contrasts(rows, sorted(((time + shift) % extent, direction) for time, direction in marks))
        for direction in DIRECTIONS:
            real[direction].append([value for value, _, _ in observed[direction]])
            shifted[direction].append([value for value, _, _ in placebo[direction]])
            candidates[direction].extend({"record_id": record, "time_s": time, "alpha_delta": value, "bolus_group": group}
                                         for value, group, time in observed[direction])
            for stratum in ("with_intervening_bolus", "no_intervening_bolus"):
                strata[direction][stratum].append([value for value, group, _ in observed[direction] if group == stratum])
    result = {"split": "validation", "measure": MEASURE, "all_annotated_events": totals,
              "observed": {direction: summarize(data, rng) for direction, data in real.items()},
              "shifted_control": {direction: summarize(data, rng) for direction, data in shifted.items()},
              "observed_by_bolus": {direction: {group: summarize(data, rng) for group, data in groups.items()}
                                    for direction, groups in strata.items()}}
    save_json(run / "trajectory.json", result)
    save_json(run / "exploratory_candidates.json", {
        direction: sorted(events, key=lambda event: -abs(event["alpha_delta"]))[:5] for direction, events in candidates.items()
    })
    return result
