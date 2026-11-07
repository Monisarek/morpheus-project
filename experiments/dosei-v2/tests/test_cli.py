from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ocon9000.__main__ import holdout, partitions


class CliTests(unittest.TestCase):
    def test_partition_is_order_independent_and_has_no_overlap(self):
        records = [f"10-{i:03d}" for i in range(171)]
        result = partitions(records)
        self.assertEqual(result, partitions(records[::-1]))
        self.assertEqual([len(ids) for ids in result.values()], [102, 34, 35])
        self.assertEqual(set(records), {record for ids in result.values() for record in ids})

    def test_holdout_release_marker_refuses_second_access(self):
        with TemporaryDirectory() as directory:
            run = Path(directory)
            (run / "holdout_release.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "already started"):
                holdout(run / "absent.zip", run)
