"""Fixed candidate, controls and held-out scoring for the MR-022 pilot."""

FEATURE_COUNT = 9
MODEL_SEED = 20261109
CONTROL_SEEDS = tuple(range(20261110, 20261120))
BOOTSTRAP_SEED = 20261120
BOOTSTRAP_DRAWS = 2000
MIN_IMPROVEMENT = 0.25
MIN_CONTROLS_WORSE = 9


def _numeric_array(np, values, dimensions):
    array = np.asarray(values)
    if (array.ndim != dimensions or not array.size
            or array.dtype.kind not in "iuf" or not np.isfinite(array).all()):
        raise ValueError("aqsol_invalid_numeric_array")
    array = array.astype(float, copy=False)
    if not np.isfinite(array).all():
        raise ValueError("aqsol_invalid_numeric_array")
    return array


def predict(train_x, train_y, test_x):
    import numpy as np
    from sklearn.ensemble import HistGradientBoostingRegressor
    from threadpoolctl import threadpool_limits

    train = _numeric_array(np, train_x, 2)
    labels = _numeric_array(np, train_y, 1)
    test = _numeric_array(np, test_x, 2)
    if len(train) != len(labels) or train.shape[1] != FEATURE_COUNT or test.shape[1] != FEATURE_COUNT:
        raise ValueError("aqsol_prediction_shape")

    def fit_and_predict(training_labels):
        model = HistGradientBoostingRegressor(
            max_iter=150,
            max_leaf_nodes=15,
            learning_rate=0.07,
            l2_regularization=1.0,
            random_state=MODEL_SEED,
        )
        model.fit(train, training_labels)
        vector = _numeric_array(np, model.predict(test), 1)
        if len(vector) != len(test):
            raise ValueError("aqsol_prediction_shape")
        return vector.tolist()

    baseline = float(np.median(labels))
    if not np.isfinite(baseline):
        raise ValueError("aqsol_nonfinite_baseline")
    with threadpool_limits(limits=1):
        candidate = fit_and_predict(labels)
        controls = [
            fit_and_predict(np.random.default_rng(seed).permutation(labels))
            for seed in CONTROL_SEEDS
        ]
    return {"baseline": [baseline] * len(test), "candidate": candidate, "controls": controls}


def score(predictions, test_y, test_groups):
    import numpy as np

    if not isinstance(predictions, dict) or set(predictions) != {"baseline", "candidate", "controls"}:
        raise ValueError("aqsol_invalid_predictions")
    labels = _numeric_array(np, test_y, 1)
    baseline = _numeric_array(np, predictions["baseline"], 1)
    candidate = _numeric_array(np, predictions["candidate"], 1)
    controls = _numeric_array(np, predictions["controls"], 2)
    groups = np.asarray(test_groups, dtype=object)
    if (len(baseline) != len(labels) or len(candidate) != len(labels)
            or controls.shape != (len(CONTROL_SEEDS), len(labels))
            or groups.shape != labels.shape
            or any(not isinstance(group, str) or not group or group != group.strip() for group in groups)):
        raise ValueError("aqsol_scoring_shape")
    scaffolds, group_index = np.unique(groups, return_inverse=True)
    group_count = len(scaffolds)
    if group_count < 2:
        raise ValueError("aqsol_bootstrap_requires_multiple_scaffolds")

    with np.errstate(over="ignore", invalid="ignore"):
        baseline_errors = np.abs(baseline - labels)
        candidate_errors = np.abs(candidate - labels)
        baseline_mae = float(baseline_errors.mean())
        candidate_mae = float(candidate_errors.mean())
        control_maes = np.abs(controls - labels).mean(axis=1)
        delta_mae = baseline_mae - candidate_mae
        group_delta = np.bincount(group_index, weights=baseline_errors - candidate_errors)
        group_rows = np.bincount(group_index)
        rng = np.random.default_rng(BOOTSTRAP_SEED)
        draws = np.empty(BOOTSTRAP_DRAWS)
        for i in range(BOOTSTRAP_DRAWS):
            drawn_groups = rng.integers(group_count, size=group_count)
            draws[i] = group_delta[drawn_groups].sum() / group_rows[drawn_groups].sum()

    if (not np.isfinite([baseline_mae, candidate_mae, delta_mae]).all()
            or not np.isfinite(control_maes).all() or not np.isfinite(draws).all()):
        raise ValueError("aqsol_nonfinite_metrics")
    interval = np.percentile(draws, [2.5, 97.5], method="linear").tolist()
    controls_worse = int((control_maes > candidate_mae).sum())
    if controls_worse < MIN_CONTROLS_WORSE:
        status = "INCONCLUSIVE_CONTROL"
    elif delta_mae >= MIN_IMPROVEMENT and interval[0] > 0:
        status = "SUPPORTED_ON_FIXED_SPLIT"
    else:
        status = "NOT_SUPPORTED"
    return {
        "status": status,
        "baseline_mae": baseline_mae,
        "candidate_mae": candidate_mae,
        "delta_mae": delta_mae,
        "ci_95": interval,
        "control_maes": control_maes.tolist(),
        "controls_worse": controls_worse,
        "test_rows": len(labels),
        "test_groups": group_count,
    }
