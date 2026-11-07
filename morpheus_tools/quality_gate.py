"""Evaluate a bounded synthetic MR-005 evidence manifest."""

import json
import sys
from math import isfinite
from pathlib import Path

from .cli import SafeArgumentParser
from .execution_checks import check_execution
from .paths import local_path
from .science_checks import check_science
from .tools.discovery import preflight


MAX_MANIFEST_BYTES = 256 * 1024
TEXT_FIELDS = (
    "version", "outcome", "ontology", "group_unit", "prediction_cutoff",
    "qc_rule", "comparator", "uncertainty", "independence_plan", "holdout_plan",
    "resume_marker", "reviewer",
)
REJECTION_GATES = {
    "unsupported_inference": {"G11", "G12"},
    "leakage": {"G02", "G03", "G04", "G05", "G06", "G13"},
    "invalid_data": {"G01", "G08", "G09", "G10", "G14", "G15", "G18"},
}


def _nonempty_text(value):
    return isinstance(value, str) and bool(value.strip())


def _review_required():
    return {"status": "BLOCKED_REVIEW", "gate_count": 0,
            "remediation": "Supply a complete synthetic manifest with valid evidence sections."}


def _controls(science, execution, blocked):
    effect = science["effect"]
    low, high = effect["interval"]
    resume = execution.get("resume", {})
    review = execution["review"]
    grounded_rejection = (
        "G21" not in blocked and review["outcome"] == "reject"
        and any(REJECTION_GATES.get(reason, set()).intersection(blocked) for reason in review["reason_codes"])
    )
    return {
        control: verdict
        for control, verdict, passed in (
            ("P01", "VERIFIED_INPUT", not blocked),
            ("P02", "PASS_HONEST_NEGATIVE", not blocked and effect["claim"] == "inconclusive" and low <= 0 <= high),
            ("P03", "PASS_RESUME", "G20" not in blocked and bool(resume["verified_reuse"])),
            ("P04", "PASS_PRIVACY", "G16" not in blocked),
            ("P05", "PASS_REJECTION", grounded_rejection),
        )
        if passed
    }


def evaluate(manifest):
    if not isinstance(manifest, dict) or type(manifest.get("schema_version")) is not int:
        return _review_required()
    if manifest["schema_version"] != 1 or manifest.get("scope") != "synthetic":
        return _review_required()
    try:
        protocol = manifest["protocol"]
        if not isinstance(protocol, dict) or any(not _nonempty_text(protocol.get(field)) for field in TEXT_FIELDS):
            return _review_required()
        for field in ("allowed_feature_types", "metrics"):
            values = protocol[field]
            if not isinstance(values, list) or not values or not all(map(_nonempty_text, values)):
                return _review_required()
        if type(protocol.get("cost_ceiling_cents")) is not int or protocol["cost_ceiling_cents"] != 0:
            return _review_required()
        science, execution = manifest["science"], manifest["execution"]
        blocked = check_science(science) | check_execution(execution)
        if protocol["group_unit"] != science["inference"]["declared_unit"]:
            blocked["G11"] = "BLOCKED_INFERENCE_UNIT"
        if protocol["comparator"] != science["baseline"]["predeclared"]:
            blocked["G14"] = "BLOCKED_BASELINE"
        if "G16" not in blocked:
            aggregate = execution["report"]["aggregate"]
            if science["effect"]["interval"] != [aggregate["ci_low"], aggregate["ci_high"]]:
                blocked["G12"] = "BLOCKED_UNSUPPORTED_CLAIM"
        if blocked and "G19" not in blocked and execution["completion"]["claim"] == "DONE":
            blocked["G19"] = "BLOCKED_FALSE_DONE"
        if (set(protocol["allowed_feature_types"]) != set(science["timing"]["allowed_kinds"])
                or protocol["reviewer"] != execution["review"]["reviewer"]):
            return _review_required()
        controls = _controls(science, execution, blocked)
        if not blocked and execution["review"]["outcome"] == "reject":
            return _review_required()
    except (KeyError, TypeError, ValueError, OverflowError):
        return _review_required()
    return {
        "status": "BLOCKED" if blocked else "VERIFIED_INPUT",
        "scope": "synthetic",
        "gate_count": 22,
        "block_count": len(blocked),
        "blocked": blocked,
        "controls": controls,
        "remediation": "Resolve the listed gates before proceeding." if blocked else "Independent scientific review remains required.",
    }


def _unique_object(pairs):
    obj = dict(pairs)
    if len(obj) != len(pairs):
        raise ValueError("duplicate_manifest_key")
    return obj


def _invalid_number(_):
    raise ValueError("nonfinite_manifest_number")


def _finite_float(text):
    value = float(text)
    return value if isfinite(value) else _invalid_number(text)


def read_manifest(path: Path):
    if str(path).startswith(("\\\\", "//")):
        raise ValueError("manifest_requires_local_path")
    path = local_path(path)
    if not path.is_file():
        raise ValueError("manifest_requires_regular_file")
    with path.open("rb") as stream:
        content = stream.read(MAX_MANIFEST_BYTES + 1)
    if len(content) > MAX_MANIFEST_BYTES:
        raise ValueError("manifest_too_large")
    return json.loads(content, object_pairs_hook=_unique_object, parse_constant=_invalid_number,
                      parse_float=_finite_float)


def main(argv=None):
    parser = SafeArgumentParser(description=__doc__)
    parser.add_argument("--preflight", action="store_true", help="Check a local Toolbox discovery report for research admission")
    parser.add_argument("manifest", type=Path)
    try:
        args = parser.parse_args(argv)
        manifest = read_manifest(args.manifest)
        result = preflight(manifest) if args.preflight else evaluate(manifest)
    except (OSError, ValueError, RecursionError):
        print('{"status":"ERROR","code":"invalid_or_unreadable_manifest"}')
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["status"] == "VERIFIED_INPUT" else 2


if __name__ == "__main__":
    sys.exit(main())
