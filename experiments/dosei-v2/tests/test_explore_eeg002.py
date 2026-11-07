import unittest

import numpy as np

from tools.explore_eeg002 import clinical_history


class ClinicalHistoryTests(unittest.TestCase):
    def test_cutoff_is_excluded_from_history_and_future_observations(self):
        past = ([(50, 0.0)], [(70, 5.0), (90, 3.0)], [40, 50, 70, 90])
        changed = (past[0] + [(100, 1.0)], past[1] + [(100, 1.0), (160, 2.0)], past[2] + [100, 160, 161])
        before, _ = clinical_history(past, 100)
        after, observed = clinical_history(changed, 100)
        self.assertEqual(before, after)
        self.assertEqual(after, (0, 0, 50, 3, -2, 10, 10, 4))
        self.assertEqual(observed, 1)

    def test_no_history_stays_missing(self):
        history, observed = clinical_history(([], [], [110]), 100)
        self.assertTrue(np.isnan(history[0]))
        self.assertEqual(history[1], 1)
        self.assertTrue(np.isnan(history[3]))
        self.assertEqual(observed, 1)
