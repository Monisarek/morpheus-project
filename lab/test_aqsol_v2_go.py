import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import aqsol_v2_go as go


PARTITION = {"train": [[[0] * 9, 1.0]], "holdout": [["g1", [0] * 9, 0.0], ["g2", [1] * 9, 2.0]]}
PREDICTED = {"baseline": [1.0, 1.0], "candidate": [0.0, 2.0], "controls": [[1.0, 1.0]] * 10}
SCORED = {"baseline_mae": 1.0, "candidate_mae": 0.0, "control_maes": [1.0] * 10,
          "test_rows": 2, "test_groups": 2}


class AqSolV2GoTests(unittest.TestCase):
    def test_bad_membership_stops_before_fit(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(go.aqsol_model, "predict") as predict:
            def rejected():
                raise ValueError("aqsol_v2_frozen_membership_mismatch")
            result = go.cycle(Path(temp) / "state", {}, rejected)
            self.assertEqual(result["stage"], "verify_v2_membership")
            self.assertEqual(result["status"], "FAILED")
            predict.assert_not_called()

    def test_unknown_fit_cannot_run_again(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(
            go.aqsol_model, "predict", side_effect=KeyboardInterrupt
        ) as predict:
            state = Path(temp) / "state"
            with self.assertRaises(KeyboardInterrupt):
                go.cycle(state, {}, lambda: PARTITION)
            result = go.cycle(state, {}, lambda: self.fail("recomputed admission"))
            self.assertEqual((result["stage"], result["reason"]),
                             ("fit_and_predict_v2_once", "external_result_unknown"))
            predict.assert_called_once()

    def test_resume_scores_saved_predictions_and_reuses_verified_result(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(
            go.aqsol_model, "predict", return_value=PREDICTED
        ) as predict, patch.object(go.aqsol_model, "score", side_effect=[ValueError(), SCORED]) as score:
            state = Path(temp) / "state"
            self.assertEqual(go.cycle(state, {}, lambda: PARTITION)["stage"], "verify_heldout_v2_aggregate")
            done = go.cycle(state, {}, lambda: self.fail("recomputed admission"))
            self.assertEqual(done["artifact"], SCORED)
            again = go.cycle(state, {}, lambda: self.fail("recomputed admission"))
            self.assertTrue(again["reused"])
            self.assertEqual(again["artifact"], SCORED)
            with self.assertRaisesRegex(ValueError, "inputs_or_stage_plan_changed"):
                go.cycle(state, {"changed": True}, lambda: self.fail("recomputed admission"))
            predict.assert_called_once_with([[0] * 9], [1.0], [[0] * 9, [1] * 9])
            self.assertEqual(score.call_count, 2)

    def test_control_mae_is_checked_against_predictions(self):
        fitted = {"predictions": PREDICTED, "labels": [0.0, 2.0], "scaffolds": ["g1", "g2"]}
        with patch.object(go.aqsol_model, "score", return_value=SCORED | {"control_maes": [0.0] * 10}):
            with self.assertRaisesRegex(ValueError, "independent_mae_check_failed"):
                go.verify(fitted)
