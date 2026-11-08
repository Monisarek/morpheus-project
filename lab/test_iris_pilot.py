import json
from pathlib import Path
from shutil import copytree
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import iris_pilot
import lab


class IrisPilotTests(unittest.TestCase):
    def test_cold_reproduction_matches_public_evidence_and_resume_skips_compute(self):
        with TemporaryDirectory() as root:
            state = Path(root) / "state"
            first = lab.run_pilot(state)
            with patch("iris_pilot.experiment", side_effect=AssertionError("recomputed")) as compute:
                second = lab.run_pilot(state)
                compute.assert_not_called()
            independent_state = lab.run_pilot(Path(root) / "independent")
        evidence = json.loads((iris_pilot.ROOT / "evidence/iris-sepal-v1.json").read_text(encoding="utf-8"))
        self.assertEqual(first["status"], "COMPLETED")
        self.assertEqual(first["artifact"], evidence)
        self.assertEqual(independent_state["artifact"], evidence)
        self.assertFalse(independent_state["reused"])
        self.assertTrue(second["reused"])
        self.assertEqual(second["artifact"], evidence)
        self.assertEqual(evidence["scientific_review"], "AWAITING_LYRA")
        self.assertTrue(evidence["negative_control_ok"])
        self.assertEqual(evidence["result"], "NOT_SUPPORTED_ON_FIXED_SPLIT")

    def test_mismatched_input_is_rejected_before_processing(self):
        with TemporaryDirectory() as root:
            base = Path(root)
            for name in ("fixtures", "protocols"):
                copytree(iris_pilot.ROOT / name, base / name)
            fixture = base / "fixtures/iris.csv"
            fixture.write_bytes(fixture.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "public_fixture_integrity"):
                iris_pilot.inputs(base)

    def test_verifier_rejects_different_test_membership(self):
        protocol, rows = iris_pilot.inputs()
        partition = iris_pilot.split(protocol, rows)
        result = iris_pilot.experiment(protocol, rows, partition)
        result["test"][0] = partition[0][0]
        with self.assertRaisesRegex(ValueError, "invalid_pilot_split"):
            iris_pilot.review(protocol, rows, result)
