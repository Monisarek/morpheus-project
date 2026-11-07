"""Post-hoc grouped comparisons using all previously opened DOSE-I records."""

import argparse
from bisect import bisect_left, bisect_right
from collections import defaultdict
import csv
from pathlib import Path

import numpy as np
from sklearn.model_selection import StratifiedGroupKFold, cross_val_predict
from threadpoolctl import threadpool_limits

from ocon9000.models import CONTEXT, SEED, _logistic, _save_report, _validate


HISTORY = ("last_soc", "soc_unknown", "soc_age", "last_moaas", "moaas_change", "moaas_age",
           "observation_age", "observations_60s")
ARTIFACT_WARNINGS = {"large_sample_jump", "line_power_50hz", "line_power_60hz"}


def clinical_history(events, time):
    soc, scores, observations = events
    soc_end = bisect_left(soc, (time,))
    score_end = bisect_left(scores, (time,))
    obs_end = bisect_left(observations, time)
    state_time, state = soc[soc_end - 1] if soc_end else (np.nan, np.nan)
    score_time, score = scores[score_end - 1] if score_end else (np.nan, np.nan)
    change = score - scores[score_end - 2][1] if score_end > 1 else np.nan
    last_observation = observations[obs_end - 1] if obs_end else np.nan
    recent = obs_end - bisect_left(observations, time - 60)
    history = (state, float(not soc_end), time - state_time, score, change, time - score_time,
               time - last_observation, recent)
    future_count = bisect_right(observations, time + 60) - bisect_right(observations, time)
    return history, future_count


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as stream:
        yield from csv.DictReader(stream)


def load_cohort(source):
    events = defaultdict(lambda: ([], [], set()))
    for name in ("events.csv", "holdout_events.csv"):
        for row in read_csv(source / name):
            kind = row["event_type"]
            if kind not in {"LOC", "ROC", "MOAAS"}:
                continue
            soc, scores, observations = events[row["record_id"]]
            time = float(row["time_s"])
            observations.add(time)
            if kind == "MOAAS":
                scores.append((time, float(row["value"])))
            else:
                soc.append((time, float(kind == "ROC")))
    events = {group: tuple(sorted(values) for values in event) for group, event in events.items()}
    rows, seen, recordings = [], set(), set()
    eeg = None
    for name in ("features.csv", "holdout_features.csv"):
        for row in read_csv(source / name):
            group, time = row["record_id"], float(row["time_s"])
            if (group, time) in seen:
                raise ValueError("Duplicate recording/time across EEG-001 artifacts")
            seen.add((group, time))
            recordings.add(group)
            if row["eligibility"] != "eligible" or row["qc"] not in {"PASS", "WARN"}:
                continue
            history, future_count = clinical_history(events[group], time)
            if not future_count or row["target"] not in {"0", "1"}:
                raise ValueError("Model window has no valid observed outcome")
            columns = tuple(sorted(key for key in row if key.startswith("eeg_")))
            if not columns or (eeg is not None and columns != eeg):
                raise ValueError("Inconsistent EEG columns")
            eeg = columns
            numeric = tuple(float(row[key]) if row[key] else np.nan for key in (*CONTEXT, *eeg))
            rows.append((group, time, int(row["target"]), (*numeric, *history),
                         not (set(row["reasons"].split(";")) & ARTIFACT_WARNINGS), future_count >= 2))
    rows.sort(key=lambda row: (row[0], row[1]))
    if not rows:
        raise ValueError("Empty common cohort")
    groups, _, labels, values, clean, frequent = zip(*rows)
    return (*map(np.asarray, (groups, labels, values, clean, frequent)), len(seen), len(recordings), eeg)


def predict(values, labels, groups, eeg_count):
    context = list(range(len(CONTEXT)))
    eeg = list(range(len(CONTEXT), len(CONTEXT) + eeg_count))
    history = list(range(len(CONTEXT) + eeg_count, values.shape[1]))
    models = {"last_state": history[:2], "time_dose": context, "eeg_only": eeg,
              "eeg_time_dose": context + eeg, "clinical_history": context + history,
              "eeg_clinical_history": context + eeg + history}
    probabilities = {key: np.full(len(labels), np.nan) for key in ("frequency", *models)}
    alerts = {key: np.zeros(len(labels), dtype=bool) for key in models}
    outer = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=SEED)
    with threadpool_limits(limits=1):
        for fit, score in outer.split(values, labels, groups):
            if set(groups[fit]) & set(groups[score]) or np.isfinite(probabilities["frequency"][score]).any():
                raise ValueError("Outer folds overlap")
            probabilities["frequency"][score] = labels[fit].mean()
            inner = StratifiedGroupKFold(n_splits=4, shuffle=True, random_state=SEED)
            folds = list(inner.split(values[fit], labels[fit], groups[fit]))
            for name, columns in models.items():
                x = values[:, columns]
                model = _logistic()
                inner_predictions = cross_val_predict(model, x[fit], labels[fit], cv=folds, method="predict_proba")[:, 1]
                threshold = np.quantile(inner_predictions[labels[fit] == 0], 0.9, method="higher")
                p = model.fit(x[fit], labels[fit]).predict_proba(x[score])[:, 1]
                probabilities[name][score] = p
                alerts[name][score] = p > threshold
    if any(not np.isfinite(p).all() for p in probabilities.values()):
        raise ValueError("Incomplete OOF predictions")
    return probabilities, alerts


def calibration(labels, prediction):
    bins = np.minimum((prediction * 5).astype(int), 4)
    return [{"bin": i, "n": int(mask.sum()), "mean_prediction": float(prediction[mask].mean()),
             "observed_frequency": float(labels[mask].mean())}
            for i in range(5) if (mask := bins == i).any()]


def analyze(source, output):
    groups, labels, values, clean, frequent, total, records, eeg = load_cohort(source)
    probabilities, alerts = predict(values, labels, groups, len(eeg))
    cohorts = {}
    for name, mask in {"primary": np.ones(len(labels), dtype=bool), "no_jump_or_line_warning": clean,
                       "at_least_two_observation_times": frequent}.items():
        y = labels[mask]
        preds = {key: p[mask] for key, p in probabilities.items()}
        scores, primary, reps = _validate(y, groups[mask], preds, ("eeg_clinical_history", "clinical_history"))
        cohorts[name] = {"recordings": len(set(groups[mask])), "windows": len(y), "positive": int(y.sum()),
                         "fraction_of_grid_windows": len(y) / total, "models": scores, "primary_comparison": primary,
                         "bootstrap_replicates": reps,
                         "calibration": {key: calibration(y, p) for key, p in preds.items()},
                         "operating_points": {key: {"fpr": float(a[mask][y == 0].mean()),
                                                   "sensitivity": float(a[mask][y == 1].mean())}
                                              for key, a in alerts.items()}}
    report = {"status": "EXPLORATORY", "formerly_open_holdout_reused": True, "resampling_unit": "recording",
              "recordings_parsed": records, "grid_windows": total, "outer_folds": 5, "inner_folds": 4,
              "clinical_history_columns": list(HISTORY), "cohorts": cohorts}
    output.mkdir(parents=True, exist_ok=True)
    return _save_report(output, "exploratory.json", report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="Local EEG-001 run with both feature/event exports")
    parser.add_argument("--output", required=True, type=Path, help="Directory for aggregate results")
    args = parser.parse_args()
    analyze(args.source, args.output)


if __name__ == "__main__":
    main()
