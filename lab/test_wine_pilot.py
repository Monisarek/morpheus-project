import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import wine_pilot
from check_registry_history import extends_history


class WinePilotTests(unittest.TestCase):
    def test_cold_replay_matches_evidence_and_resume_skips_calculation(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = wine_pilot.run(root / "a")
            with patch("wine_pilot.calculate", side_effect=AssertionError("recomputed")) as compute:
                second = wine_pilot.run(root / "a")
                compute.assert_not_called()
            independent = wine_pilot.run(root / "b")
        expected = json.loads((wine_pilot.ROOT / "evidence/wine-color-v1.json").read_bytes())
        self.assertEqual(first["artifact"], expected)
        self.assertEqual(independent["artifact"], expected)
        self.assertTrue(second["reused"])
        self.assertEqual(expected["scientific_review"], "AWAITING_LYRA")

    def test_history_only_allows_appending(self):
        self.assertTrue(extends_history("one\ntwo\n", "one\ntwo\nthree\n"))
        self.assertFalse(extends_history("one\ntwo\n", "one\nchanged\n"))
