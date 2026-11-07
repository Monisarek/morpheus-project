"""Compare local scientific evidence against the frozen protocol."""

from math import isfinite
import re


_FINGERPRINT = re.compile(r"[0-9a-fA-F]{64}")
_PARTITIONS = {"train", "validation", "holdout"}
_TIME_UNITS = {"s", "ms", "us", "ns"}
_DOSE_UNITS = {"mg", "ug", "mg/kg", "ug/kg", "mg/kg/min", "ug/kg/min", "mg/kg/h", "ug/kg/h"}
_ROLES = {"predictor", "label", "future_response", "outcome"}
_GROUP_UNITS = {"subject", "session", "recording", "window"}


def _text(value):
    if type(value) is not str or not value.strip() or value != value.strip():
        raise ValueError("invalid_science_evidence")
    return value


def _proof(value):
    return value is not None and bool(_text(value))


def _choice(value, allowed):
    if _text(value) not in allowed:
        raise ValueError("invalid_science_evidence")
    return value


def _flag(value):
    if type(value) is not bool:
        raise ValueError("invalid_science_evidence")
    return value


def _number(value):
    if type(value) is int or (type(value) is float and isfinite(value)):
        return value
    raise ValueError("invalid_science_evidence")


def _items(value, *, required=False):
    if type(value) is not list or (required and not value):
        raise ValueError("invalid_science_evidence")
    return value


def _split_checks(rows):
    subjects, sessions, contents = {}, {}, {}
    partitions = set()
    subject_overlap = session_overlap = False
    for row in _items(rows, required=True):
        partition = _choice(row["partition"], _PARTITIONS)
        subject, session = _text(row["subject"]), _text(row["session"])
        fingerprint = _text(row["fingerprint"])
        if not _FINGERPRINT.fullmatch(fingerprint):
            raise ValueError("invalid_science_evidence")
        partitions.add(partition)
        subject_overlap |= subjects.setdefault(subject, partition) != partition
        session_overlap |= sessions.setdefault(session, partition) != partition
        session_overlap |= contents.setdefault(fingerprint.lower(), partition) != partition
    if not {"train", "holdout"} <= partitions:
        raise ValueError("invalid_science_evidence")
    return subject_overlap, session_overlap


def check_science(evidence):
    """Return failed gate IDs and fixed reason codes, without evidence values."""
    source = evidence["source"]
    approved = _flag(source["approved"])
    restricted = _flag(source["restricted"])
    license_proof = _proof(source["license_proof"])
    dua_proof = _proof(source["dua_proof"])
    subject_overlap, session_overlap = _split_checks(evidence["splits"])

    timing = evidence["timing"]
    decision, axis, unit = _number(timing["decision"]), _text(timing["axis"]), _text(timing["unit"])
    invalid_axis = unit not in _TIME_UNITS or not _proof(timing["sync_proof"])
    allowed_kinds = {_text(kind) for kind in _items(timing["allowed_kinds"], required=True)}
    seen_kinds = set()
    future_leak = target_leak = False
    for feature in _items(evidence["features"], required=True):
        at = _number(feature["observed_at"])
        kind, role = _text(feature["kind"]), _choice(feature["role"], _ROLES)
        seen_kinds.add(kind)
        feature_axis, feature_unit = _text(feature["axis"]), _text(feature["unit"])
        comparable = feature_axis == axis and feature_unit == unit and unit in _TIME_UNITS
        invalid_axis |= not comparable
        future_leak |= comparable and at > decision
        target_leak |= role != "predictor"

    fit = {_choice(value, _PARTITIONS) for value in _items(evidence["fit_partitions"])}
    negative = evidence["negative_control"]
    _text(negative["metric"])
    observed, limit = _number(negative["observed"]), _number(negative["limit"])
    direction = _choice(negative["direction"], {"higher", "lower"})
    suspicious = observed > limit if direction == "higher" else observed < limit
    qc_roles = {_choice(role, _ROLES) for role in _items(evidence["qc_dependencies"])}
    dose = evidence["dose"]
    observed_dose = {_text(value) for value in _items(dose["observed_units"])}
    expected_dose = dose["expected_unit"]
    if expected_dose is not None:
        _text(expected_dose)
    dose_used = "dose" in seen_kinds or bool(observed_dose)
    invalid_dose = dose_used and (expected_dose not in _DOSE_UNITS or observed_dose != {expected_dose})

    inference = evidence["inference"]
    groups = {_choice(inference[field], _GROUP_UNITS) for field in ("declared_unit", "reported_unit", "resampling_unit")}
    effect = evidence["effect"]
    claim = _choice(effect["claim"], {"proven_improvement", "inconclusive", "negative", "exploratory"})
    low, high = map(_number, _items(effect["interval"], required=True))
    if low > high:
        raise ValueError("invalid_science_evidence")
    holdout = evidence["holdout"]
    accesses = [_choice(purpose, {"final_evaluation", "exploration", "tuning"}) for purpose in _items(holdout["accesses"])]
    adaptive = _flag(holdout["adaptive_tuning"])
    baseline = evidence["baseline"]
    predeclared, evaluated = baseline["predeclared"], baseline["evaluated"]
    baseline_matches = _proof(predeclared) and _proof(evaluated) and predeclared == evaluated

    checks = {
        "G01": (not approved or not license_proof or (restricted and not dua_proof), "BLOCKED_LICENSE"),
        "G02": (subject_overlap, "BLOCKED_GROUP_LEAKAGE"),
        "G03": (session_overlap, "BLOCKED_REVIEW"),
        "G04": (future_leak, "BLOCKED_FUTURE_LEAKAGE"),
        "G05": (target_leak, "BLOCKED_TARGET_LEAKAGE"),
        "G06": (bool(fit - {"train"}), "BLOCKED_FIT_LEAKAGE"),
        "G07": (suspicious, "BLOCKED_REVIEW"),
        "G08": (bool(qc_roles - {"predictor"}), "BLOCKED_SELECTION_BIAS"),
        "G09": (invalid_axis, "BLOCKED_TIME_AXIS"),
        "G10": (invalid_dose, "BLOCKED_UNITS"),
        "G11": (len(groups) != 1, "BLOCKED_INFERENCE_UNIT"),
        "G12": (claim == "proven_improvement" and low <= 0, "BLOCKED_UNSUPPORTED_CLAIM"),
        "G13": (adaptive or len(accesses) > 1 or any(p != "final_evaluation" for p in accesses), "BLOCKED_HOLDOUT_REUSE"),
        "G14": (not baseline_matches, "BLOCKED_BASELINE"),
    }
    if seen_kinds - allowed_kinds and not target_leak:
        raise ValueError("invalid_science_evidence")
    return {gate: code for gate, (failed, code) in checks.items() if failed}
