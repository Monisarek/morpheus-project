"""Frozen synthetic evidence for MR-005 G01–G14, P01 and P02."""

import unittest

from morpheus_tools.science_checks import check_science


def valid_science_evidence():
    return {
        "source": {"restricted": False, "approved": True, "license_proof": "synthetic-license", "dua_proof": None},
        "splits": [
            {"subject": "synthetic-1", "session": "session-a", "fingerprint": "a" * 64, "partition": "train"},
            {"subject": "synthetic-2", "session": "session-b", "fingerprint": "b" * 64, "partition": "holdout"},
        ],
        "timing": {"decision": 10, "axis": "elapsed", "unit": "s", "sync_proof": "synthetic-sync",
                   "allowed_kinds": ["eeg", "dose"]},
        "features": [
            {"kind": "eeg", "role": "predictor", "observed_at": 9, "axis": "elapsed", "unit": "s"},
            {"kind": "dose", "role": "predictor", "observed_at": 10, "axis": "elapsed", "unit": "s"},
        ],
        "fit_partitions": ["train"],
        "negative_control": {"metric": "roc_auc", "observed": 0.50, "limit": 0.60, "direction": "higher"},
        "qc_dependencies": ["predictor"],
        "dose": {"expected_unit": "mg/kg", "observed_units": ["mg/kg"]},
        "inference": {"declared_unit": "subject", "reported_unit": "subject", "resampling_unit": "subject"},
        "effect": {"claim": "proven_improvement", "interval": [0.01, 0.03]},
        "holdout": {"accesses": ["final_evaluation"], "adaptive_tuning": False},
        "baseline": {"predeclared": "synthetic-clinical", "evaluated": "synthetic-clinical"},
    }


class ScienceChecksTests(unittest.TestCase):
    def setUp(self):
        self.evidence = valid_science_evidence()

    def assert_blocked(self, gate, reason):
        self.assertEqual(check_science(self.evidence), {gate: reason})

    def test_G01_license_and_dua(self):
        self.evidence["source"]["restricted"] = True
        self.assert_blocked("G01", "BLOCKED_LICENSE")
        self.evidence["source"].update(dua_proof="synthetic-dua", license_proof=None)
        self.assert_blocked("G01", "BLOCKED_LICENSE")

    def test_G02_subject_crosses_split(self):
        self.evidence["splits"][1]["subject"] = "synthetic-1"
        self.assert_blocked("G02", "BLOCKED_GROUP_LEAKAGE")

    def test_G03_renamed_session_keeps_fingerprint(self):
        self.evidence["splits"][1]["fingerprint"] = "A" * 64
        self.assert_blocked("G03", "BLOCKED_REVIEW")

    def test_G04_future_predictor(self):
        self.evidence["features"][0]["observed_at"] = 10.001
        self.assert_blocked("G04", "BLOCKED_FUTURE_LEAKAGE")

    def test_G05_target_as_feature(self):
        for role in ("label", "future_response"):
            with self.subTest(role=role):
                self.evidence["features"][0]["role"] = role
                self.assert_blocked("G05", "BLOCKED_TARGET_LEAKAGE")

    def test_G06_preprocessing_fit_on_holdout(self):
        self.evidence["fit_partitions"].append("holdout")
        self.assert_blocked("G06", "BLOCKED_FIT_LEAKAGE")

    def test_G07_suspicious_negative_control(self):
        self.evidence["negative_control"]["observed"] = 0.95
        self.assert_blocked("G07", "BLOCKED_REVIEW")
        self.evidence["negative_control"].update(direction="lower", observed=0.01, limit=0.10)
        self.assert_blocked("G07", "BLOCKED_REVIEW")

    def test_G08_qc_depends_on_outcome(self):
        self.evidence["qc_dependencies"].append("outcome")
        self.assert_blocked("G08", "BLOCKED_SELECTION_BIAS")

    def test_G09_clock_and_time_units(self):
        self.evidence["features"][0]["axis"] = "unmapped"
        self.assert_blocked("G09", "BLOCKED_TIME_AXIS")
        self.evidence["features"][0].update(axis="elapsed", unit="ms")
        self.assert_blocked("G09", "BLOCKED_TIME_AXIS")

    def test_G10_incompatible_dose_scale(self):
        self.evidence["dose"]["observed_units"] = ["ug/kg"]
        self.assert_blocked("G10", "BLOCKED_UNITS")

    def test_G11_window_pseudoreplication(self):
        self.evidence["inference"]["resampling_unit"] = "window"
        self.assert_blocked("G11", "BLOCKED_INFERENCE_UNIT")

    def test_G12_confidence_interval_does_not_support_proven_claim(self):
        self.evidence["effect"]["interval"] = [-0.01, 0.03]
        self.assert_blocked("G12", "BLOCKED_UNSUPPORTED_CLAIM")
        self.evidence["effect"]["interval"] = [0, 0.03]
        self.assert_blocked("G12", "BLOCKED_UNSUPPORTED_CLAIM")

    def test_G13_holdout_peeking_and_adaptation(self):
        self.evidence["holdout"]["accesses"].append("final_evaluation")
        self.assert_blocked("G13", "BLOCKED_HOLDOUT_REUSE")
        self.evidence["holdout"] = {"accesses": ["final_evaluation"], "adaptive_tuning": True}
        self.assert_blocked("G13", "BLOCKED_HOLDOUT_REUSE")

    def test_G14_missing_or_substituted_baseline(self):
        self.evidence["baseline"]["predeclared"] = None
        self.assert_blocked("G14", "BLOCKED_BASELINE")
        self.evidence["baseline"]["predeclared"] = "different-baseline"
        self.assert_blocked("G14", "BLOCKED_BASELINE")

    def test_P01_clean_input_at_cutoff(self):
        self.assertEqual(check_science(self.evidence), {})

    def test_P02_inconclusive_interval_is_honest(self):
        self.evidence["effect"].update(claim="inconclusive", interval=[-0.01, 0.03])
        self.assertEqual(check_science(self.evidence), {})

    def test_malformed_timestamp_and_missing_metadata_fail_closed(self):
        self.evidence["features"][0]["observed_at"] = True
        with self.assertRaises(ValueError):
            check_science(self.evidence)
        del self.evidence["source"]
        with self.assertRaises(KeyError):
            check_science(self.evidence)
