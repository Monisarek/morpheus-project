"""Preregistered variant adding past changes in relative band power."""

import csv


HYPOTHESIS_ID = "H01"


def add_band_deltas(source, output):
    with source.open(newline="", encoding="utf-8") as src, output.open("w", newline="", encoding="utf-8") as dst:
        reader = csv.DictReader(src)
        fields = reader.fieldnames or []
        bands = [key for key in fields if key.startswith(("eeg_1_rel_", "eeg_2_rel_"))]
        if not bands:
            raise ValueError("The base file needs relative band power columns")
        writer = csv.DictWriter(dst, fieldnames=[*fields, *(f"eeg_delta15_{key[4:]}" for key in bands)])
        writer.writeheader()
        previous = None
        for row in reader:
            contiguous = (previous and row["record_id"] == previous["record_id"] and row["split"] == previous["split"]
                          and float(row["time_s"]) - float(previous["time_s"]) == 15
                          and row["qc"] in {"PASS", "WARN"} and previous["qc"] in {"PASS", "WARN"})
            deltas = {f"eeg_delta15_{key[4:]}": float(row[key]) - float(previous[key])
                      for key in bands if contiguous and row[key] and previous[key]}
            writer.writerow({**row, **deltas})
            previous = row
