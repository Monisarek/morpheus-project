import csv
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ocon9000.experiment import add_band_deltas


class ExperimentTests(unittest.TestCase):
    def test_delta_never_crosses_qc_gap_or_group(self):
        with TemporaryDirectory() as directory:
            source, output = (Path(directory) / name for name in ("source.csv", "output.csv"))
            source.write_text("record_id,split,time_s,qc,eeg_1_rel_alpha\n"
                              "a,train,30,PASS,0.25\na,train,45,PASS,0.5\na,train,60,FAIL,\n"
                              "a,train,75,PASS,1\nb,validation,90,PASS,0.5\n", encoding="utf-8")
            add_band_deltas(source, output)
            with output.open(newline="", encoding="utf-8") as stream:
                values = [row["eeg_delta15_1_rel_alpha"] for row in csv.DictReader(stream)]
            self.assertEqual(values, ["", "0.25", "", "", ""])
