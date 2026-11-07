import json
import unittest
from argparse import Namespace
from pathlib import Path
from tempfile import TemporaryDirectory

from morpheus_tools.execution_checks import check_execution
from morpheus_tools.tools import compare, tabular


def valid_execution_evidence():
    return {
        "scan": {"status": "failed_check", "scan_complete": True, "claims_absence": True, "empty_subsets": ["check_1"]},
        "report": {"privacy_reviewed": True, "aggregate": {"n_units": 20, "estimate": 0.01, "ci_low": -0.01, "ci_high": 0.03}},
        "export": {"inventory_complete": True, "items": [{"classification": "aggregate", "secret_scan": "clean"}]},
        "artifact": {"frozen_reference_verified": True, "status": "ok", "match": True,
                     "identical_files": 1, "different_files": 0, "only_left_count": 0, "only_right_count": 0},
        "completion": {"claim": "OPEN", "reproducible_evidence": False},
        "resume": {"checkpoint_verified": True, "completed_paid": ["attempt-a"],
                   "scheduled": ["attempt-b"], "verified_reuse": ["attempt-a"]},
        "review": {"producer": "synthetic-author", "reviewer": "synthetic-reviewer",
                   "hidden_judge_seen": False, "evidence_bound": True,
                   "outcome": "accept", "reason_codes": ["method_valid"]},
        "transfer": {"destination": "none", "classification": "none", "approved": False},
    }


class ExecutionGateTests(unittest.TestCase):
    def setUp(self):
        self.evidence = valid_execution_evidence()

    def test_G15_partial_toolbox_scan_cannot_prove_absence(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.csv"
            path.write_text("split\ntrain\nholdout\n", encoding="utf-8")
            args = Namespace(input=str(path), max_rows=1, expect_subset=["split=holdout"])
            result = tabular.execute(args, "empty_check")
            args.max_rows = 2
            complete = tabular.execute(args, "empty_check")
        self.assertEqual(result["status"], "partial")
        self.evidence["scan"] = {**result, "claims_absence": True}
        self.assertEqual(check_execution(self.evidence), {"G15": "BLOCKED_INCOMPLETE_SCAN"})
        self.evidence["scan"]["claims_absence"] = False
        self.assertEqual(check_execution(self.evidence), {})
        self.evidence["scan"] = {**complete, "claims_absence": True}
        self.assertEqual(check_execution(self.evidence), {"G15": "BLOCKED_INCOMPLETE_SCAN"})

    def test_G16_identifiers_rows_and_secrets_not_public(self):
        aggregate = self.evidence["report"]["aggregate"]
        for key, value in (("participant_id", "faux-id"), ("rows", [[12]]), ("token", "faux-token")):
            with self.subTest(key=key):
                self.evidence["report"]["aggregate"] = {**aggregate, key: value}
                self.assertEqual(check_execution(self.evidence), {"G16": "BLOCKED_PRIVACY"})
        self.evidence["report"] = {"privacy_reviewed": True, "aggregate": aggregate, "token": "faux"}
        self.assertEqual(check_execution(self.evidence), {"G16": "BLOCKED_PRIVACY"})

    def test_G17_restricted_export_blocked(self):
        for classification in ("restricted", "examiner_key", "secret"):
            with self.subTest(classification=classification):
                self.evidence["export"]["items"] = [{"classification": classification, "secret_scan": "clean"}]
                self.assertEqual(check_execution(self.evidence), {"G17": "BLOCKED_EXPORT"})

    def test_G18_real_toolbox_artifact_comparison(self):
        with TemporaryDirectory() as directory:
            left, right = Path(directory) / "frozen", Path(directory) / "observed"
            left.write_text("frozen", encoding="utf-8")
            right.write_text("mutate", encoding="utf-8")
            args = Namespace(left=str(left), right=str(right), max_files=2)
            mismatch = compare.execute(args, "compare")
            right.write_text("frozen", encoding="utf-8")
            match = compare.execute(args, "compare")
        self.evidence["artifact"] = {**mismatch, "frozen_reference_verified": True}
        self.assertEqual(check_execution(self.evidence), {"G18": "BLOCKED_INTEGRITY"})
        self.evidence["artifact"] = {**match, "frozen_reference_verified": True}
        self.assertEqual(check_execution(self.evidence), {})

    def test_G19_done_requires_reproducible_independent_evidence(self):
        self.evidence["completion"]["claim"] = "DONE"
        self.assertEqual(check_execution(self.evidence), {"G19": "BLOCKED_FALSE_DONE"})
        self.evidence["completion"]["reproducible_evidence"] = True
        self.evidence["review"].update(outcome="reject", reason_codes=["unsupported_inference"])
        self.assertEqual(check_execution(self.evidence), {"G19": "BLOCKED_FALSE_DONE"})
        self.evidence["review"]["evidence_bound"] = False
        self.assertEqual(check_execution(self.evidence),
                         {"G19": "BLOCKED_FALSE_DONE", "G21": "BLOCKED_NONINDEPENDENT_REVIEW"})

    def test_G20_paid_computation_not_replayed(self):
        self.evidence["resume"]["scheduled"] = ["attempt-a"]
        self.assertEqual(check_execution(self.evidence), {"G20": "BLOCKED_DUPLICATE_RUN"})

    def test_G21_no_self_review_or_judge_peeking(self):
        review = self.evidence["review"].copy()
        for changed in ({"reviewer": review["producer"]}, {"hidden_judge_seen": True}):
            with self.subTest(changed=changed):
                self.evidence["review"] = {**review, **changed}
                self.assertEqual(check_execution(self.evidence), {"G21": "BLOCKED_NONINDEPENDENT_REVIEW"})

    def test_G22_unapproved_free_tier_transfer(self):
        self.evidence["transfer"] = {"destination": "external", "classification": "restricted",
                                     "approved": False, "free_tier": True}
        self.assertEqual(check_execution(self.evidence), {"G22": "BLOCKED_TRANSFER"})

    def test_P03_resume_reuses_verified_finished_work(self):
        with TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "checkpoint.json"
            checkpoint.write_text(json.dumps({"attempt-a": "VERIFIED_PAID"}), encoding="utf-8")
            ledger = json.loads(checkpoint.read_text(encoding="utf-8"))
        completed = [key for key, state in ledger.items() if state == "VERIFIED_PAID"]
        pending = [key for key in ("attempt-a", "attempt-b") if key not in completed]
        self.evidence["resume"].update(completed_paid=completed, scheduled=pending, verified_reuse=completed)
        invoked = []
        self.assertEqual(check_execution(self.evidence), {})
        for key in pending:
            invoked.append(key)
        self.assertEqual(invoked, ["attempt-b"])
        self.assertEqual(list(ledger), ["attempt-a"])
        self.evidence["resume"]["scheduled"].append("attempt-a")
        self.assertEqual(check_execution(self.evidence), {"G20": "BLOCKED_DUPLICATE_RUN"})

    def test_P04_aggregate_report_passes(self):
        self.assertEqual(check_execution(self.evidence), {})
        self.evidence["report"]["privacy_reviewed"] = False
        self.assertEqual(check_execution(self.evidence), {"G16": "BLOCKED_PRIVACY"})

    def test_P05_grounded_independent_rejection_passes(self):
        self.evidence["review"].update(outcome="reject", reason_codes=["unsupported_inference"])
        self.assertEqual(check_execution(self.evidence), {})
        self.assertEqual(self.evidence["review"]["outcome"], "reject")
        self.assertEqual(self.evidence["completion"]["claim"], "OPEN")
        self.evidence["review"]["reason_codes"] = ["method_valid"]
        self.assertEqual(check_execution(self.evidence), {"G21": "BLOCKED_NONINDEPENDENT_REVIEW"})

    def test_missing_sections_are_never_a_pass(self):
        self.assertEqual(list(check_execution({})), [f"G{i}" for i in range(15, 23)])
