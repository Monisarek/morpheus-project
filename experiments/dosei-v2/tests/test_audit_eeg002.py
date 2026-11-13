from io import StringIO
import unittest

from tools.audit_eeg002 import clinical_event, duplicate_rows, window_outcome


class AuditTests(unittest.TestCase):
    def test_transition_at_index_excluded_and_at_end_included(self):
        clinical = [(30, "LOC"), (45, "MOAAS"), (90, "ROC"), (90.004, "LOC")]
        self.assertEqual(window_outcome(30, 90.004, clinical), ("eligible", "1", ["MOAAS", "ROC"]))
        self.assertEqual(window_outcome(30, 90, clinical), ("right_censored", "", []))
        self.assertEqual(window_outcome(30, 100, clinical[:1]), ("no_observation_in_horizon", "", []))
        self.assertEqual(window_outcome(30, 100, clinical[:2]), ("eligible", "0", ["MOAAS"]))

    def test_swapped_direction_or_wrong_source_is_rejected(self):
        good = {"event_type": "ROC", "label_source": "raw/SOC", "value": "1.0"}
        self.assertTrue(clinical_event(good))
        with self.assertRaises(ValueError):
            clinical_event({**good, "event_type": "LOC"})
        with self.assertRaises(ValueError):
            clinical_event({**good, "label_source": "derived/pEEG"})

    def test_raw_duplicates_distinguish_redundancy_from_conflict(self):
        content = StringIO("Time,SOC,MOAAS\na,0,2\na,0,2\nb,,3\nb,1,4\nc,,5\n")
        counts, columns, competing = duplicate_rows(content)
        self.assertEqual(counts, {"adjacent_duplicate_pairs": 2, "exact_pairs": 1, "conflicting_pairs": 1})
        self.assertEqual(columns, {"SOC": 1, "MOAAS": 1})
        self.assertEqual(competing, {"MOAAS": 1})
