import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from morpheus_tools.quality_gate import MAX_MANIFEST_BYTES, evaluate, main
from test_morpheus_execution_checks import valid_execution_evidence
from test_morpheus_science_checks import valid_science_evidence


def valid_manifest():
    manifest = {
        "schema_version": 1,
        "scope": "synthetic",
        "protocol": {
            "version": "fixture-1",
            "outcome": "synthetic binary label",
            "ontology": "synthetic two-state probe",
            "group_unit": "subject",
            "prediction_cutoff": "per-row decision timestamp",
            "allowed_feature_types": ["eeg", "dose"],
            "qc_rule": "past-only signal QC",
            "comparator": "synthetic-clinical",
            "metrics": ["average precision"],
            "uncertainty": "paired group interval",
            "independence_plan": "reviewer separate from executor",
            "holdout_plan": "one fixed evaluation",
            "cost_ceiling_cents": 0,
            "resume_marker": "fixture-stage-v1",
            "reviewer": "synthetic-reviewer",
        },
        "science": valid_science_evidence(),
        "execution": valid_execution_evidence(),
    }
    manifest["execution"]["report"]["aggregate"]["ci_low"] = 0.01
    return manifest


class QualityGateTests(unittest.TestCase):
    def call(self, text):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "manifest.json"
            path.write_text(text, encoding="utf-8")
            output = io.StringIO()
            with redirect_stdout(output):
                code = main([str(path)])
        return code, json.loads(output.getvalue()), output.getvalue()

    def test_complete_synthetic_manifest_only_verifies_input(self):
        code, result, _ = self.call(json.dumps(valid_manifest()))
        self.assertEqual(code, 0)
        self.assertEqual(result["status"], "VERIFIED_INPUT")
        self.assertEqual(result["gate_count"], 22)
        self.assertEqual(result["block_count"], 0)
        self.assertEqual(result["controls"], {"P01": "VERIFIED_INPUT", "P03": "PASS_RESUME", "P04": "PASS_PRIVACY"})

    def test_honest_inconclusive_and_independent_rejection_are_distinct(self):
        manifest = valid_manifest()
        effect = manifest["science"]["effect"]
        effect.update(claim="inconclusive", interval=[-0.01, 0.03])
        manifest["execution"]["report"]["aggregate"]["ci_low"] = -0.01
        self.assertEqual(evaluate(manifest)["controls"]["P02"], "PASS_HONEST_NEGATIVE")
        effect["claim"] = "proven_improvement"
        manifest["execution"]["review"].update(outcome="reject", reason_codes=["unsupported_inference"])
        result = evaluate(manifest)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["blocked"], {"G12": "BLOCKED_UNSUPPORTED_CLAIM"})
        self.assertEqual(result["controls"]["P05"], "PASS_REJECTION")
        self.assertNotIn("P02", result["controls"])

    def test_unsubstantiated_rejection_and_done_never_qualify(self):
        manifest = valid_manifest()
        manifest["execution"]["review"].update(outcome="reject", reason_codes=["unsupported_inference"])
        self.assertEqual(evaluate(manifest)["status"], "BLOCKED_REVIEW")
        manifest["execution"]["review"].update(outcome="accept", reason_codes=["method_valid"])
        manifest["execution"]["completion"].update(claim="DONE", reproducible_evidence=True)
        manifest["execution"]["report"]["aggregate"]["ci_low"] = -0.01
        result = evaluate(manifest)
        self.assertEqual(result["blocked"], {"G12": "BLOCKED_UNSUPPORTED_CLAIM", "G19": "BLOCKED_FALSE_DONE"})

    def test_unc_manifest_is_rejected_without_opening_it(self):
        from unittest.mock import patch

        with patch("morpheus_tools.quality_gate.local_path") as resolve, redirect_stdout(io.StringIO()):
            self.assertEqual(main([r"\\server\share\synthetic.json"]), 1)
        resolve.assert_not_called()

    def test_missing_protocol_and_non_synthetic_scope_fail_closed(self):
        incomplete = valid_manifest()
        del incomplete["protocol"]["prediction_cutoff"]
        self.assertEqual(evaluate(incomplete)["status"], "BLOCKED_REVIEW")
        out_of_scope = valid_manifest()
        out_of_scope["scope"] = "SYNTHETIC_ONLY_PRIVATE_MARKER"
        code, result, output = self.call(json.dumps(out_of_scope))
        self.assertEqual(code, 2)
        self.assertEqual(result["status"], "BLOCKED_REVIEW")
        self.assertNotIn(out_of_scope["scope"], output)

    def test_malformed_duplicate_nonfinite_and_oversize_json(self):
        for text in ('{"x":', '{"x":1,"x":2}', '{"x":NaN}', '{"x":1e999}', " " * (MAX_MANIFEST_BYTES + 1)):
            with self.subTest(kind=text[:10]):
                code, result, _ = self.call(text)
                self.assertEqual(code, 1)
                self.assertEqual(result["status"], "ERROR")

    def test_group_unit_and_baseline_must_match_protocol(self):
        manifest = valid_manifest()
        manifest["science"]["inference"] = dict.fromkeys(
            ("declared_unit", "reported_unit", "resampling_unit"), "window"
        )
        manifest["science"]["baseline"] = dict.fromkeys(("predeclared", "evaluated"), "changed-baseline")
        code, result, output = self.call(json.dumps(manifest))
        self.assertEqual(code, 2)
        self.assertEqual(result["blocked"], {"G11": "BLOCKED_INFERENCE_UNIT", "G14": "BLOCKED_BASELINE"})
        self.assertNotIn("changed-baseline", output)


if __name__ == "__main__":
    unittest.main()
