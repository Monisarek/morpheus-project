"""MR-005 execution and publication checks on local, bounded evidence."""
from math import isfinite


PUBLIC_CLASSES = {"code", "documentation", "aggregate", "synthetic"}
DATA_CLASSES = PUBLIC_CLASSES | {"restricted", "participant_ids", "examiner_key", "secret"}
REVIEW_OUTCOMES = {"accept", "reject", "indeterminate"}
REVIEW_REASONS = {"unsupported_inference", "leakage", "invalid_data", "inconclusive", "method_valid"}


def _section(evidence, key):
    value = evidence.get(key)
    return value if isinstance(value, dict) else {}


def _keys(values):
    if not isinstance(values, list) or not all(
        isinstance(value, str) and value and value == value.strip() for value in values
    ):
        return None
    return set(values) if len(set(values)) == len(values) else None


def _valid_scan(scan):
    complete = scan.get("scan_complete")
    absence = scan.get("claims_absence")
    status = scan.get("status")
    return (
        type(complete) is bool
        and type(absence) is bool
        and status in ("ok", "partial", "failed_check")
        and (status != "ok" or complete)
        and (status != "partial" or not complete)
        and (not absence or (complete and status == "failed_check" and bool(_keys(scan.get("empty_subsets")))))
    )


def _public_report(report):
    aggregate = report.get("aggregate")
    if (
        set(report) != {"privacy_reviewed", "aggregate"}
        or report["privacy_reviewed"] is not True
        or not isinstance(aggregate, dict)
    ):
        return False
    if set(aggregate) != {"n_units", "estimate", "ci_low", "ci_high"}:
        return False
    count = aggregate["n_units"]
    numbers = (aggregate["ci_low"], aggregate["estimate"], aggregate["ci_high"])
    return (
        type(count) is int
        and count > 0
        and all(type(value) is int or (type(value) is float and isfinite(value)) for value in numbers)
        and numbers[0] <= numbers[2]
    )


def _safe_export(export):
    items = export.get("items")
    return (
        set(export) == {"inventory_complete", "items"}
        and export.get("inventory_complete") is True
        and isinstance(items, list)
        and all(
            isinstance(item, dict)
            and set(item) == {"classification", "secret_scan"}
            and item["classification"] in tuple(PUBLIC_CLASSES)
            and item["secret_scan"] == "clean"
            for item in items
        )
    )


def _verified_artifact(artifact):
    counts = [artifact.get(name) for name in ("different_files", "only_left_count", "only_right_count")]
    return (
        artifact.get("frozen_reference_verified") is True
        and artifact.get("status") == "ok"
        and artifact.get("match") is True
        and all(type(count) is int and count == 0 for count in counts)
        and type(artifact.get("identical_files")) is int
        and artifact["identical_files"] > 0
    )


def _valid_resume(resume):
    completed, rerun, reused = (_keys(resume.get(key)) for key in ("completed_paid", "scheduled", "verified_reuse"))
    return (
        resume.get("checkpoint_verified") is True
        and completed is not None and rerun is not None and reused is not None
        and completed == reused and completed.isdisjoint(rerun)
    )


def _independent_review(review):
    identities = _keys([review.get("producer"), review.get("reviewer")])
    reasons = _keys(review.get("reason_codes"))
    outcome = review.get("outcome")
    return (
        identities is not None
        and len({identity.casefold() for identity in identities}) == 2
        and review.get("hidden_judge_seen") is False
        and review.get("evidence_bound") is True
        and outcome in tuple(REVIEW_OUTCOMES)
        and reasons is not None and bool(reasons) and reasons <= REVIEW_REASONS
        and (outcome != "reject" or bool(reasons - {"method_valid", "inconclusive"}))
    )


def _safe_transfer(transfer):
    destination, kind = transfer.get("destination"), transfer.get("classification")
    return (
        (destination == "none" and kind == "none")
        or (destination == "local" and kind in tuple(DATA_CLASSES))
        or (destination == "external" and kind in tuple(PUBLIC_CLASSES) and transfer.get("approved") is True)
    )


def check_execution(evidence: dict) -> dict[str, str]:
    """Return only stable gate IDs/codes. Caller must attest provenance independently."""
    if not isinstance(evidence, dict):
        evidence = {}
    scan, report, export, artifact, completion, resume, review, transfer = (
        _section(evidence, key)
        for key in ("scan", "report", "export", "artifact", "completion", "resume", "review", "transfer")
    )
    integrity = _verified_artifact(artifact)
    independent = _independent_review(review)
    completion_ok = completion.get("claim") == "OPEN" or (
        completion.get("claim") == "DONE"
        and completion.get("reproducible_evidence") is True
        and integrity
        and independent
        and review.get("outcome") == "accept"
    )
    return {
        gate: code
        for gate, code, passed in (
            ("G15", "BLOCKED_INCOMPLETE_SCAN", _valid_scan(scan)),
            ("G16", "BLOCKED_PRIVACY", _public_report(report)),
            ("G17", "BLOCKED_EXPORT", _safe_export(export)),
            ("G18", "BLOCKED_INTEGRITY", integrity),
            ("G19", "BLOCKED_FALSE_DONE", completion_ok),
            ("G20", "BLOCKED_DUPLICATE_RUN", _valid_resume(resume)),
            ("G21", "BLOCKED_NONINDEPENDENT_REVIEW", independent),
            ("G22", "BLOCKED_TRANSFER", _safe_transfer(transfer)),
        )
        if not passed
    }
