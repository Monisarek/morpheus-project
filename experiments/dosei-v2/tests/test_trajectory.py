import unittest

from ocon9000.trajectory import MEASURE, contrasts


class TrajectoryTests(unittest.TestCase):
    def test_pre_post_excludes_overlapping_transitions_and_tracks_doses(self):
        windows = [{"time_s": t, "qc": "PASS", MEASURE: t / 100, "dose_mg": 10 if t >= 90 else 0}
                   for t in range(30, 165, 15)]
        isolated = contrasts(windows, [(61, "LOC")])
        self.assertAlmostEqual(isolated["LOC"][0][0], 0.45)
        self.assertEqual(isolated["LOC"][0][1], "with_intervening_bolus")
        self.assertEqual(isolated["LOC"][0][2], 61)
        self.assertFalse(contrasts(windows, [(61, "LOC"), (70, "ROC")]))
