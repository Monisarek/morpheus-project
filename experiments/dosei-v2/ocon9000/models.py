"""Fit the preregistered baselines on train and score validation by record."""

import csv
import json
from collections import Counter
from pathlib import Path
from tempfile import NamedTemporaryFile

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold, cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits


SEED = 9000
BOOTSTRAP_REPLICATES = 1000
CONTEXT = ("elapsed_s", "dose_mg", "dose_60s_mg", "dose_age_s")
SINGLE_BAND = "eeg_1_rel_alpha"
METRICS = ("average_precision", "auroc", "brier")
QC_LEVELS = {"PASS", "WARN", "FAIL", "UNKNOWN"}


def _save_report(output, filename, report):
    content = json.dumps(report, indent=2, allow_nan=False) + "\n"
    stream = NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=output, delete=False)
    temporary = Path(stream.name)
    try:
        with stream:
            stream.write(content)
        temporary.replace(output / filename)
    finally:
        temporary.unlink(missing_ok=True)
    return report


def _read_rows(path, split_names=("train", "validation")):
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames or []
        required = {"record_id", "split", "time_s", "target", "qc", *CONTEXT, SINGLE_BAND}
        if not required.issubset(fields) or len(fields) != len(set(fields)):
            raise ValueError("Feature CSV has missing or duplicate columns")
        features = (*CONTEXT, *sorted(name for name in fields if name.startswith("eeg_")))
        splits = {name: [] for name in split_names}
        group_splits = {}
        index = set()
        for row in reader:
            if None in row or None in row.values():
                raise ValueError(f"Malformed feature row {reader.line_num}")
            split, record_id, qc, target = (row[k].strip() for k in ("split", "record_id", "qc", "target"))
            if split not in splits:
                raise ValueError(f"Unexpected split {split!r}; expected {' or '.join(split_names)}")
            if not record_id or qc not in QC_LEVELS or target not in {"0", "1", ""}:
                raise ValueError(f"Invalid record, QC or target at feature row {reader.line_num}")
            if group_splits.setdefault(record_id, split) != split:
                raise ValueError("A recording appears in more than one split")
            time_s = float(row["time_s"])
            if not np.isfinite(time_s) or time_s < 0 or (record_id, time_s) in index:
                raise ValueError(f"Invalid or duplicate index time at feature row {reader.line_num}")
            index.add((record_id, time_s))
            values = None
            if target and qc in {"PASS", "WARN"}:
                values = [float(row[name]) if row[name].strip() else np.nan for name in features]
                if not np.isfinite(values[:3]).all() or np.isinf(values).any():
                    raise ValueError(f"Invalid numeric feature at feature row {reader.line_num}")
            splits[split].append((record_id, time_s, target, qc, values))
        for rows in splits.values():
            rows.sort(key=lambda row: (row[0], row[1]))
    return features, splits


def _cohort(rows):
    qc_by_target = {target: Counter(qc for _, _, observed, qc, _ in rows if observed == target)
                    for target in ("0", "1", "")}
    included = [(record_id, target, values) for record_id, _, target, _, values in rows if values is not None]
    groups, labels, values = zip(*included) if included else ([], [], [])
    summary = {
        "records_total": len({record_id for record_id, *_ in rows}),
        "records_included": len(set(groups)),
        "windows_total": len(rows),
        "windows_included": len(included),
        "windows_excluded": len(rows) - len(included),
        "positive_windows_included": labels.count("1"),
        "qc_by_target": {target or "unobserved": dict(counts) for target, counts in qc_by_target.items()},
    }
    if len(set(groups)) < 2 or len(set(labels)) < 2:
        raise ValueError("Each split needs at least two recordings and both observed classes after QC")
    return np.asarray(values), np.asarray(labels, dtype=int), np.asarray(groups), summary


def _logistic():
    return make_pipeline(SimpleImputer(strategy="median", keep_empty_features=True), StandardScaler(),
                         LogisticRegression(max_iter=1000, random_state=SEED))


def _scores(labels, predictions):
    return np.array((average_precision_score(labels, predictions), roc_auc_score(labels, predictions),
                     brier_score_loss(labels, predictions)))


def _ci(replicates):
    return np.quantile(replicates, (0.025, 0.975), axis=0).T.tolist()


def _validate(labels, groups, predictions, contrast=("eeg_context_logistic", "context_logistic")):
    group_rows = [np.flatnonzero(groups == group) for group in np.unique(groups)]
    rng = np.random.default_rng(SEED)
    replicates = []
    for _ in range(BOOTSTRAP_REPLICATES):
        sampled = rng.integers(0, len(group_rows), size=len(group_rows))
        indices = np.concatenate([group_rows[i] for i in sampled])
        sampled_labels = labels[indices]
        if sampled_labels.min() == sampled_labels.max():
            continue
        replicates.append([_scores(sampled_labels, pred[indices]) for pred in predictions.values()])
    if not replicates:
        raise ValueError("No cluster bootstrap replicate included both classes")
    replicates = np.asarray(replicates)
    scores = {}
    for model_index, (name, pred) in enumerate(predictions.items()):
        scores[name] = {
            key: {"value": float(value), "ci95": interval}
            for key, value, interval in zip(METRICS, _scores(labels, pred), _ci(replicates[:, model_index, :]))
        }
    names = list(predictions)
    combined, context = (names.index(name) for name in contrast)
    paired = replicates[:, combined, 0] - replicates[:, context, 0]
    primary = {
        "contrast": " minus ".join(contrast),
        "metric": "average_precision",
        "value": scores[names[combined]]["average_precision"]["value"] - scores[names[context]]["average_precision"]["value"],
        "ci95": _ci(paired),
    }
    return scores, primary, len(replicates)


def _cv_folds(train_x, train_y, train_groups):
    limit = min(5, len(set(train_groups)), int(np.bincount(train_y).min()))
    for count in range(limit, 1, -1):
        folds = list(StratifiedGroupKFold(n_splits=count, shuffle=True, random_state=SEED)
                     .split(train_x, train_y, train_groups))
        if all(len(set(train_y[fit])) == 2 for fit, _ in folds):
            return folds
    return []


def _false_positive_control(train_y, train_prob, score_y, score_prob):
    negative = train_prob[train_y == 0]
    threshold = float(np.quantile(negative, 0.9, method="higher"))
    positive = score_prob > threshold
    return {
        "target_train_false_positive_rate": 0.1,
        "train_oof_threshold_exclusive": threshold,
        "train_oof_false_positive_rate": float((negative > threshold).mean()),
        "evaluation_false_positive_rate": float(positive[score_y == 0].mean()),
        "evaluation_sensitivity": float(positive[score_y == 1].mean()),
        "unit": "window",
    }


def run_baseline(path: Path, output: Path, final_path: Path | None = None) -> dict:
    features, splits = _read_rows(path)
    fit_rows = splits["train"]
    score_rows = splits["validation"]
    fit_split, score_split = "train", "validation"
    if final_path is not None:
        holdout_features, holdout = _read_rows(final_path, ("holdout",))
        if features != holdout_features:
            raise ValueError("Development and holdout feature schemas differ")
        fit_rows = fit_rows + score_rows
        score_rows = holdout["holdout"]
        if {row[0] for row in fit_rows}.intersection(row[0] for row in score_rows):
            raise ValueError("A holdout recording appears in development data")
        fit_split, score_split = "train_and_validation", "holdout"
    train_x, train_y, train_groups, train_summary = _cohort(fit_rows)
    val_x, val_y, val_groups, val_summary = _cohort(score_rows)
    clinical = slice(0, len(CONTEXT))
    eeg = slice(len(CONTEXT), None)
    forest = make_pipeline(SimpleImputer(strategy="median", keep_empty_features=True),
                           RandomForestClassifier(n_estimators=100, max_depth=8, min_samples_leaf=5,
                                                  random_state=SEED, n_jobs=1))
    models = {
        "context_logistic": (_logistic(), clinical),
        "single_band_logistic": (_logistic(), [features.index(SINGLE_BAND)]),
        "eeg_logistic": (_logistic(), eeg),
        "eeg_context_logistic": (_logistic(), slice(None)),
        "eeg_random_forest": (forest, eeg),
    }
    predictions = {"train_prevalence": np.full(len(val_y), train_y.mean())}
    folds = _cv_folds(train_x, train_y, train_groups)
    cv_scores = {}
    operating_points = {}
    with threadpool_limits(limits=1):
        for name, (model, columns) in models.items():
            x = train_x[:, columns]
            predictions[name] = model.fit(x, train_y).predict_proba(val_x[:, columns])[:, 1]
            if folds:
                oof = cross_val_predict(model, x, train_y, cv=folds, method="predict_proba")[:, 1]
                cv_scores[name] = dict(zip(METRICS, _scores(train_y, oof).tolist()))
                operating_points[name] = _false_positive_control(train_y, oof, val_y, predictions[name])
    scores, primary, replicates = _validate(val_y, val_groups, predictions)
    report = {
        "group_unit": "recording",
        "scoring_unit": "window",
        "fit_split": fit_split,
        "evaluation_split": score_split,
        "seed": SEED,
        "eeg_features": list(features[eeg]),
        "context_features": list(CONTEXT),
        "cohort": {fit_split: train_summary, score_split: val_summary},
        "models": scores,
        "primary_comparison": primary,
        "bootstrap": {"requested": BOOTSTRAP_REPLICATES, "valid": replicates, "resampling_unit": "recording"},
        "train_grouped_cv": {"folds": len(folds), "out_of_fold_scores": cv_scores},
        "operating_points": operating_points,
    }
    filename = "holdout_metrics.json" if final_path is not None else "metrics.json"
    return _save_report(output, filename, report)


def _shifted_labels(labels, group_rows, rng):
    shifted = labels.copy()
    for indices in group_rows:
        if len(indices) > 1:
            shifted[indices] = np.roll(labels[indices], rng.integers(1, len(indices)))
    return shifted


def falsify(path: Path, output: Path) -> dict:
    """Probe time structure and ascertainment on validation, with frozen baselines."""
    _, splits = _read_rows(path)
    train_x, train_y, _, _ = _cohort(splits["train"])
    val_x, val_y, val_groups, _ = _cohort(splits["validation"])
    context = slice(0, len(CONTEXT))
    flags = ("interpolated_at_most_5pct", "large_sample_jump", "line_power_50hz", "line_power_60hz")
    quality = {split: [] for split in splits}
    with path.open(newline="", encoding="utf-8-sig") as stream:
        for row in csv.DictReader(stream):
            qc = row["qc"].strip()
            if row["target"].strip() and qc in {"PASS", "WARN"}:
                reasons = set(row.get("reasons", "").split(";"))
                quality[row["split"].strip()].append([qc == "WARN", *(flag in reasons for flag in flags)])
    with threadpool_limits(limits=1):
        context_pred = _logistic().fit(train_x[:, context], train_y).predict_proba(val_x[:, context])[:, 1]
        combined_pred = _logistic().fit(train_x, train_y).predict_proba(val_x)[:, 1]
        quality_pred = _logistic().fit(quality["train"], train_y).predict_proba(quality["validation"])[:, 1]
    scores, primary, valid = _validate(val_y, val_groups, {
        "context_logistic": context_pred,
        "eeg_context_logistic": combined_pred,
        "quality_only_logistic": quality_pred,
    })
    group_rows = [np.flatnonzero(val_groups == group) for group in np.unique(val_groups)]
    rng = np.random.default_rng(SEED)
    null_deltas = []
    for _ in range(BOOTSTRAP_REPLICATES):
        shifted = _shifted_labels(val_y, group_rows, rng)
        delta = average_precision_score(shifted, combined_pred) - average_precision_score(shifted, context_pred)
        null_deltas.append(delta)
    report = {
        "evaluation_split": "validation",
        "seed": SEED,
        "circular_shift": {
            "metric": "average_precision_delta_combined_minus_context",
            "observed": primary["value"],
            "shifted_interval95": _ci(null_deltas),
            "replicates": len(null_deltas),
            "records_with_nonconstant_target": sum(len(set(val_y[idx])) == 2 for idx in group_rows),
            "empirical_fraction_at_least_observed": float(np.mean(np.array(null_deltas) >= primary["value"])),
            "scope": "descriptive null on the retained index sequence; unequal gaps and nonstationarity limit exchangeability",
        },
        "quality_only": {"inputs": ["WARN versus PASS", *flags], "bootstrap_valid": valid,
                         "models": scores["quality_only_logistic"]},
    }
    return _save_report(output, "falsification.json", report)


def compare_variant(base_path: Path, variant_path: Path, output: Path) -> dict:
    """Score a registered EEG feature extension on the unchanged validation cohort."""
    base_features, base = _read_rows(base_path)
    variant_features, variant = _read_rows(variant_path)
    added = sorted(set(variant_features).difference(base_features))
    if not added or not set(base_features).issubset(variant_features):
        raise ValueError("Variant must extend the baseline feature schema")
    shared_columns = [variant_features.index(name) for name in base_features]
    for split, base_rows in base.items():
        variant_rows = variant[split]
        if [row[:4] for row in base_rows] != [row[:4] for row in variant_rows]:
            raise ValueError("Variant changed the split, index, target or QC")
        for base_row, variant_row in zip(base_rows, variant_rows):
            values = base_row[4]
            if values is not None and not np.array_equal(values, np.array(variant_row[4])[shared_columns], equal_nan=True):
                raise ValueError("Variant changed an existing feature")
    predictions = {}
    with threadpool_limits(limits=1):
        for name, splits in (("baseline", base), ("variant", variant)):
            train_x, train_y, _, _ = _cohort(splits["train"])
            val_x, val_y, val_groups, _ = _cohort(splits["validation"])
            predictions[name] = _logistic().fit(train_x, train_y).predict_proba(val_x)[:, 1]
    scores, primary, valid = _validate(val_y, val_groups, predictions, contrast=("variant", "baseline"))
    report = {
        "evaluation_split": "validation",
        "added_eeg_features": added,
        "models": scores,
        "primary_comparison": primary,
        "bootstrap_valid": valid,
        "acceptance_rule": {"minimum_delta_ap": 0.01, "lower_ci95_strictly_above": 0.0},
        "accepted": primary["value"] >= 0.01 and primary["ci95"][0] > 0,
    }
    return _save_report(output, "variant_metrics.json", report)
