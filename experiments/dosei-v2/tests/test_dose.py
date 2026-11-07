from datetime import datetime, timedelta
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from zipfile import ZipFile

import numpy as np

from ocon9000.dose import blocks, metadata, profile, recordings


HEADER = "Time,Intellivue/EEG_1-V,Intellivue/EEG_2,SOC,MOAAS,Propofol\n"
START = datetime(2022, 1, 1, 23, 59, 58)


def sample(index, payload):
    time = START + timedelta(milliseconds=4 * index)
    return f"{time.isoformat(sep=' ', timespec='milliseconds')},{payload}\n"


class DoseReaderTest(TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.archive = Path(directory.name, "recordings.zip")

    def write(self, content):
        with ZipFile(self.archive, "w") as archive:
            archive.writestr("data/10_003.csv", content)

    def test_grid_units_events_and_missing_values(self):
        self.write(
            HEADER + sample(0, "0.00001,20,,,") + sample(1, ",,,4,")
            + sample(2, ",,0,,10") + sample(3, "0.00003,40,,,")
            + sample(4, "0.00007,,1,,")
        )
        self.assertEqual(recordings(self.archive, verify=False), ["10-003"])
        [(start, end, eeg, events)] = blocks(self.archive, "10-003")
        self.assertEqual((start, end), (0, 0.02))
        np.testing.assert_allclose(eeg, [[10, 20], [30, 40], [70, np.nan]])
        self.assertEqual([e["event_type"] for e in events], ["MOAAS", "LOC", "Propofol", "ROC"])
        self.assertEqual([e["time_s"] for e in events], [0.004, 0.008, 0.008, 0.016])
        self.assertEqual(events[1]["label_source"], "raw/SOC")
        self.assertEqual(profile("10-003")["subject_id"], "UNKNOWN")
        self.assertEqual(profile("10-003")["reference"], "bipolar")

    def test_next_block_starts_at_boundary_without_future_sample(self):
        self.write(
            HEADER + "".join(sample(i, ",,,,") for i in range(3749))
            + sample(3749, "0.00001,1,,,") + sample(3750, "0.00009,9,1,,")
        )
        first, second = blocks(self.archive, "10-003")
        self.assertEqual(first[1], 15)
        self.assertEqual(second[0], 15)
        self.assertEqual(first[2].shape, (1875, 2))
        np.testing.assert_allclose(first[2][-1], [10, 1])
        np.testing.assert_allclose(second[2][0], [90, 9])
        self.assertEqual(first[3], [])
        self.assertEqual(second[3][0]["time_s"], 15)

    def test_rejects_bad_clock_and_wrong_event_codes(self):
        for index in (0, 2):
            with self.subTest(index=index):
                self.write(HEADER + sample(0, ",,,,") + sample(index, ",,,,"))
                with self.assertRaisesRegex(ValueError, "time grid"):
                    list(blocks(self.archive, "10-003"))
        self.write(HEADER + sample(0, ",,2,,"))
        with self.assertRaisesRegex(ValueError, "SOC code"):
            list(blocks(self.archive, "10-003"))

    def test_rejects_missing_channel_ragged_and_unverified_archive(self):
        self.write(HEADER.replace("Intellivue/EEG_1-V", "OtherChannel") + sample(0, ",,,,"))
        with self.assertRaisesRegex(ValueError, "missing channel"):
            list(blocks(self.archive, "10-003"))
        self.write(HEADER + sample(0, ",,,"))
        with self.assertRaisesRegex(ValueError, "ragged"):
            list(blocks(self.archive, "10-003"))
        with self.assertRaisesRegex(ValueError, "MD5"):
            recordings(self.archive)

    def test_rejects_duplicate_ids(self):
        self.write(HEADER)
        with ZipFile(self.archive, "a") as archive:
            archive.writestr("other/10-003.csv", HEADER)
        with self.assertRaisesRegex(ValueError, "duplicate record ID"):
            recordings(self.archive, verify=False)

    def test_duplicate_observation_preserves_saturation(self):
        self.write(HEADER + sample(0, "0.00002,20,,,") + sample(1, "0.00001,-187.5,,,"))
        [(_, _, eeg, _)] = blocks(self.archive, "10-003")
        np.testing.assert_allclose(eeg, [[20, -187.5]])

    def test_metadata_only_parses_allowed_outcomes(self):
        with ZipFile(self.archive, "w") as archive:
            archive.writestr("metadata/DOSE-I_metadata.csv",
                             ",length,SOC_trans,MOAAS_sum,residual_errors,version\n"
                             "003,181,2,3,['Trail'],4.1.1\n"
                             "004,180,0,2,,4.1.1\n"
                             "005,invalid,invalid,invalid,invalid,invalid\n")
        checksum = hashlib.md5(self.archive.read_bytes(), usedforsecurity=False).hexdigest()
        with patch("ocon9000.dose.METADATA_MD5", checksum):
            result = metadata(self.archive, {"10-003", "10-004"})
        self.assertEqual(result, {"10-003": {"length": 181, "SOC_trans": 2, "MOAAS_sum": 3,
                                               "residual_errors": ["Trail"], "version": "4.1.1"},
                                  "10-004": {"length": 180, "SOC_trans": 0, "MOAAS_sum": 2,
                                               "residual_errors": [], "version": "4.1.1"}})
