import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from ocon9000.models import CONTEXT, SINGLE_BAND, _shifted_labels, compare_variant, falsify, run_baseline


HEADER = ("record_id", "split", "time_s", "target", "qc", *CONTEXT, SINGLE_BAND, "eeg_test", "future_target")


def write_features(path, groups):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(HEADER)
        for record_id, split in groups:
            for index in range(12):
                target = index % 2
                time_s = index * 15
                qc = "FAIL" if index == 0 else "PASS"
                writer.writerow((record_id, split, time_s, target, qc, time_s, 0, 0, "", target,
                                 target + index / 100, target))


class ModelsTest(unittest.TestCase):
    @patch("ocon9000.models.BOOTSTRAP_REPLICATES", 20)
    def test_fixed_comparisons_and_grouped_uncertainty(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "features.csv"
            groups = [("a", "train"), ("b", "train"), ("c", "validation"), ("d", "validation")]
            write_features(path, groups)
            first = run_baseline(path, root)
            self.assertEqual(json.loads((root / "metrics.json").read_text()), first)
            self.assertEqual(first, run_baseline(path, root))
            self.assertEqual(first["bootstrap"]["resampling_unit"], "recording")
            self.assertEqual(first["bootstrap"]["valid"], 20)
            self.assertEqual(len(first["models"]), 6)
            self.assertEqual(first["cohort"]["validation"]["windows_excluded"], 2)
            self.assertEqual(first["eeg_features"], [SINGLE_BAND, "eeg_test"])
            self.assertGreater(first["primary_comparison"]["ci95"][0], 0)

    def test_rejects_leaked_groups_and_holdout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "features.csv"
            for groups, message in [([("a", "train"), ("a", "validation")], "more than one split"),
                                    ([("a", "holdout")], "Unexpected split")]:
                write_features(path, groups)
                with self.assertRaisesRegex(ValueError, message):
                    run_baseline(path, root)
            self.assertFalse((root / "metrics.json").exists())

    @patch("ocon9000.models.BOOTSTRAP_REPLICATES", 10)
    def test_explicit_holdout_uses_all_development_groups(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            development = root / "development.csv"
            holdout = root / "holdout.csv"
            groups = [("a", "train"), ("b", "train"), ("c", "validation"), ("d", "validation")]
            write_features(development, groups)
            write_features(holdout, [("c", "holdout"), ("e", "holdout")])
            with self.assertRaisesRegex(ValueError, "holdout recording"):
                run_baseline(development, root, final_path=holdout)
            write_features(holdout, [("e", "holdout"), ("f", "holdout")])
            report = run_baseline(development, root, final_path=holdout)
            self.assertEqual(report["evaluation_split"], "holdout")
            self.assertEqual(report["cohort"]["train_and_validation"]["records_included"], 4)
            self.assertTrue((root / "holdout_metrics.json").is_file())
            self.assertFalse((root / "metrics.json").exists())

    @patch("ocon9000.models.BOOTSTRAP_REPLICATES", 10)
    def test_shift_null_preserves_group_counts(self):
        labels = np.array([0, 1, 1, 0, 0, 0, 0])
        groups = [np.array([0, 1, 2]), np.array([3, 4, 5]), np.array([6])]
        shifted = _shifted_labels(labels, groups, np.random.default_rng(9000))
        self.assertEqual([labels[group].sum() for group in groups], [shifted[group].sum() for group in groups])
        self.assertFalse(np.array_equal(shifted, labels))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "features.csv"
            write_features(path, [("a", "train"), ("b", "train"), ("c", "validation"), ("d", "validation")])
            report = falsify(path, root)
            self.assertEqual(report["circular_shift"]["replicates"], 10)
            self.assertEqual(report["circular_shift"]["records_with_nonconstant_target"], 2)
            self.assertEqual(report["quality_only"]["models"]["auroc"]["value"], 0.5)

    @patch("ocon9000.models.BOOTSTRAP_REPLICATES", 10)
    def test_variant_requires_identical_targets_and_cohort(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / "base.csv"
            variant = root / "variant.csv"
            groups = [("a", "train"), ("b", "train"), ("c", "validation"), ("d", "validation")]
            write_features(base, groups)
            with base.open(newline="", encoding="utf-8") as stream:
                header, *rows = csv.reader(stream)
            def write_variant():
                with variant.open("w", newline="", encoding="utf-8") as stream:
                    writer = csv.writer(stream)
                    writer.writerow([*header, "eeg_constant"])
                    writer.writerows([*row, 1] for row in rows)
            write_variant()
            self.assertFalse(compare_variant(base, variant, root)["accepted"])
            rows[1][3] = "0"
            write_variant()
            with self.assertRaisesRegex(ValueError, "target or QC"):
                compare_variant(base, variant, root)
