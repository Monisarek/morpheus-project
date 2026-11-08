import json
import unittest
from unittest.mock import patch

import aqsol_v2 as v2


class AqSolV2Tests(unittest.TestCase):
    def test_target_cap_and_strict_improvement(self):
        with patch.object(v2, "scaffold_key", side_effect=lambda group: (group, group)):
            cases = [
                ({"a": 13, "b": 13, "c": 7, "z": 67}, {"a", "c"}),   # cap
                ({"a": 17, "b": 6, "c": 3, "z": 74}, {"a", "c"}),   # tie
                ({"a": 12, "b": 12, "z": 76}, {"a", "b"}),          # closer overshoot
            ]
            for sizes, expected in cases:
                self.assertEqual(v2.select_holdout(sizes), expected)
        self.assertEqual(v2.row_limits(4779), (956, 1194))

    def test_order_is_deterministic_and_reference_rejects_altered_selection(self):
        sizes = {"C1CC1": 8, "c1ccccc1": 9, "C1CCC1": 13, "C1CCCC1": 70}
        expected = v2.select_holdout(sizes)
        self.assertEqual(v2.select_holdout(dict(reversed(list(sizes.items())))), expected)
        v2.verify_decisions(sizes, expected)
        with self.assertRaisesRegex(ValueError, "v2_scaffold_decision_mismatch"):
            v2.verify_decisions(sizes, expected ^ {"C1CC1"})
        with patch.object(v2, "sha256") as hash_function:
            hash_function.return_value.digest.return_value = bytes(32)
            self.assertEqual(v2.select_holdout({"z": 80, "b": 20, "a": 20}), {"a"})

    def test_disjointness_and_minimum_in_both_partitions(self):
        train = [(f"t{i}", f"tg{i % 100}") for i in range(400)]
        holdout = [(f"h{i}", f"hg{i}") for i in range(100)]
        self.assertEqual(v2.audit_partitions(train, holdout)["holdout_fraction"], 0.20)
        for altered_train, altered_test in (
            (train, holdout[:-1]),
            ([(name, f"tg{i % 99}") for i, (name, _) in enumerate(train)], holdout),
            (train, [(train[0][0], holdout[0][1]), *holdout[1:]]),
            (train, [(holdout[0][0], train[0][1]), *holdout[1:]]),
            (train + [(f"extra{i}", "tg0") for i in range(200)], holdout),
        ):
            with self.assertRaisesRegex(ValueError, "v2_split_blocked"):
                v2.audit_partitions(altered_train, altered_test)

    def test_v1_protocol_invariants(self):
        parent = json.loads(v2.v1.PROTOCOL.read_bytes())
        protocol = json.loads((v2.ROOT / "protocols/aqsol-solubility-v2.json").read_bytes())
        v2.check_protocol(parent, protocol)
        with self.assertRaisesRegex(ValueError, "v2_protocol_changed_outside_split"):
            v2.check_protocol(parent, protocol | {"features": []})
