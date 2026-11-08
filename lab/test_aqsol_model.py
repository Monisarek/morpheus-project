import importlib.util
import json
import unittest
from unittest.mock import Mock, patch

import aqsol_model as pilot


HAS_NUMPY = importlib.util.find_spec("numpy") is not None
HAS_MODEL = (HAS_NUMPY and importlib.util.find_spec("sklearn") is not None
             and importlib.util.find_spec("threadpoolctl") is not None)


@unittest.skipUnless(HAS_NUMPY, "requires the AqSolDB numerical environment")
class ScoringTests(unittest.TestCase):
    def test_group_bootstrap_is_paired_row_weighted_and_reproducible(self):
        predictions = {"baseline": [1, 4, 1], "candidate": [0.5, 1, 0.5],
                       "controls": [[1, 1, 1]] * 9 + [[0.5, 1, 0.5]]}
        first = pilot.score(predictions, [0, 0, 0], ["z", "a", "z"])
        self.assertEqual(first, pilot.score(predictions, [0, 0, 0], ["z", "a", "z"]))
        self.assertEqual(first["status"], "SUPPORTED_ON_FIXED_SPLIT")
        self.assertEqual(first["controls_worse"], 9)
        self.assertEqual(first["baseline_mae"], 2.0)
        self.assertAlmostEqual(first["delta_mae"], 4 / 3)
        self.assertEqual(first["ci_95"], [0.5, 3.0])
        json.dumps(first, allow_nan=False)

    def test_control_tie_and_each_effect_threshold(self):
        predictions = {"baseline": [1, 4, 1], "candidate": [0.5, 1, 0.5],
                       "controls": [[1, 1, 1]] * 8 + [[0.5, 1, 0.5]] * 2}
        self.assertEqual(pilot.score(predictions, [0, 0, 0], ["z", "a", "z"])["status"],
                         "INCONCLUSIVE_CONTROL")
        predictions = {"baseline": [0.24, 0.24], "candidate": [0, 0], "controls": [[1, 1]] * 10}
        self.assertEqual(pilot.score(predictions, [0, 0], ["a", "z"])["status"], "NOT_SUPPORTED")
        predictions = {"baseline": [2, 0], "candidate": [0, 1], "controls": [[2, 2]] * 10}
        output = pilot.score(predictions, [0, 0], ["a", "z"])
        self.assertGreater(output["delta_mae"], 0.25)
        self.assertLess(output["ci_95"][0], 0)
        self.assertEqual(output["status"], "NOT_SUPPORTED")

    def test_invalid_holdout_and_nonfinite_values_fail(self):
        predictions = {"baseline": [1, 1], "candidate": [0, 0], "controls": [[1, 1]] * 10}
        for values, labels, groups in (
            (predictions, [0, float("nan")], ["a", "z"]),
            (predictions, [0, 0], ["a", "a"]),
            (predictions, [0, 0], ["a", 7]),
            (predictions, [0, 0], "az"),
            (predictions | {"controls": [[1, 1]] * 9}, [0, 0], ["a", "z"]),
            (predictions | {"candidate": [1e308, 1e308]}, [-1e308, 0], ["a", "z"]),
        ):
            with self.subTest(labels=labels, groups=groups), self.assertRaises(ValueError):
                pilot.score(values, labels, groups)


@unittest.skipUnless(HAS_MODEL, "requires the AqSolDB model environment")
class PredictionTests(unittest.TestCase):
    def test_fixed_model_and_training_only_permutations(self):
        import numpy as np

        model = Mock()
        model.predict.return_value = np.array([0.0, 1.0])
        train = [[float(i)] * 9 for i in range(5)]
        labels = [0.0, 1.0, 2.0, 3.0, 4.0]
        test = [[1.0] * 9, [2.0] * 9]
        with patch("sklearn.ensemble.HistGradientBoostingRegressor", return_value=model) as constructor:
            result = pilot.predict(train, labels, test)
        self.assertEqual(result["baseline"], [2.0, 2.0])
        self.assertEqual(len(result["controls"]), 10)
        self.assertEqual(constructor.call_count, 11)
        for call in constructor.call_args_list:
            self.assertEqual(call.kwargs, {"max_iter": 150, "max_leaf_nodes": 15, "learning_rate": 0.07,
                                           "l2_regularization": 1.0, "random_state": 20261109})
        self.assertEqual(model.fit.call_args_list[0].args[1].tolist(), labels)
        for seed, call in enumerate(model.fit.call_args_list[1:], 20261110):
            np.testing.assert_array_equal(call.args[0], train)
            np.testing.assert_array_equal(call.args[1], np.random.default_rng(seed).permutation(labels))
        for call in model.predict.call_args_list:
            np.testing.assert_array_equal(call.args[0], test)
        with self.assertRaises(ValueError):
            pilot.predict(train, labels, [[0.0] * 8])
