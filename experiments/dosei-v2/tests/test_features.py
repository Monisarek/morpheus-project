import unittest

import numpy as np

from ocon9000.features import build_record, window_features


class FeatureTests(unittest.TestCase):
    def setUp(self):
        time = np.arange(15 * 125) / 125
        self.block = 20 * np.column_stack([np.sin(2 * np.pi * 10 * time), np.sin(2 * np.pi * 6 * time)])

    def record(self, future_amplitude):
        for start in range(0, 105, 15):
            events = []
            if start == 30:
                events = [{"event_type": "Propofol", "time_s": 30.0, "value": 20},
                          {"event_type": "ROC", "time_s": 30.0, "value": 1}]
            if start == 90:
                events = [{"event_type": "LOC", "time_s": 90.0, "value": 0}]
            yield start, start + 15, self.block if start < 30 else self.block * future_amplitude, events

    def test_future_change_does_not_change_features_or_context(self):
        before = build_record(self.record(1))[0][0]
        after = build_record(self.record(100))[0][0]
        self.assertEqual(before, after)
        self.assertEqual(before["target"], 1)
        self.assertEqual(before["dose_mg"], 0)
        self.assertGreater(before["eeg_1_rel_alpha"], 0.99)
        self.assertGreater(before["eeg_2_rel_theta"], 0.99)

    def test_qc_flags_bad_windows(self):
        signal = np.concatenate([self.block, self.block])
        signal[0, 0] = np.nan
        self.assertEqual(window_features(signal)[1], "WARN")
        signal[0, 0] = 187.5
        self.assertEqual(window_features(signal)[1:], ("FAIL", ["saturation"]))
        signal[:300, 0] = np.nan
        self.assertEqual(window_features(signal)[1:], ("FAIL", ["missing_above_5pct"]))
