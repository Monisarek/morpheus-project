"""Check bounded windows of CC0 BrainVision data. Print aggregates only."""

import csv
import io
import json
import re
from collections import Counter
from urllib.request import Request, urlopen

import numpy as np


INDEX = "https://zarr.nemar.org/on005620/zarr/index.json"
BASE = "https://data.nemar.org/on005620/v1.0.0/"
SECONDS = 2
MAX_BYTES = 3_000_000


def fetch(url, byte_range=None):
    headers = {"Range": f"bytes={byte_range[0]}-{byte_range[1]}"} if byte_range else {}
    with urlopen(Request(url, headers=headers), timeout=20) as response:
        if byte_range:
            start, end = byte_range
            if response.status != 206 or not response.headers.get("Content-Range", "").startswith(f"bytes {start}-{end}/"):
                raise ValueError("Expected an exact HTTP byte range")
        result = response.read(MAX_BYTES + 1)
    if len(result) > MAX_BYTES or (byte_range and len(result) != end - start + 1):
        raise ValueError("Unexpected response length")
    return result


def pilot(path, offset_s):
    url = BASE + path.removesuffix(".vhdr")
    header = fetch(url + ".vhdr").decode("utf-8-sig")
    if "DataOrientation=MULTIPLEXED" not in header or "BinaryFormat=IEEE_FLOAT_32" not in header:
        raise ValueError("Expected multiplexed float32 BrainVision data")
    count = int(re.search(r"^NumberOfChannels=(\d+)", header, re.M)[1])
    rate = 1_000_000 / float(re.search(r"^SamplingInterval=([\d.]+)", header, re.M)[1])
    table_url = url.removesuffix("_eeg") + "_channels.tsv"
    channels = list(csv.DictReader(io.StringIO(fetch(table_url).decode("utf-8-sig")), delimiter="\t"))
    scales = [float(value) for value in re.findall(r"^Ch\d+=[^,]*,[^,]*,([^,]+),µV\s*$", header, re.M)]
    if len(channels) != count or len(scales) != count:
        raise ValueError("Unrecognized channel layout or units")
    eeg = [i for i, channel in enumerate(channels) if channel["type"] == "EEG"]
    if not eeg:
        raise ValueError("No EEG channels")
    samples = int(rate * SECONDS)
    start = int(rate * offset_s) * count * 4
    payload = fetch(url + ".eeg", (start, start + samples * count * 4 - 1))
    signal = np.frombuffer(payload, dtype="<f4").reshape(samples, count)[:, eeg] * np.array(scales)[eeg]
    finite = np.isfinite(signal).all(axis=0)
    inspected = signal[:, finite]
    return {
        "seconds": SECONDS,
        "source_hz": rate,
        "eeg_channels": len(eeg),
        "bytes_read": len(payload),
        "nonfinite_channels": int((~finite).sum()),
        "constant_channels": int((np.ptp(inspected, axis=0) == 0).sum()),
        "channels_peak_to_peak_gt_150_uv": int((np.ptp(inspected, axis=0) > 150).sum()),
    }


def event_inventory():
    index = json.loads(fetch("https://zarr.nemar.org/on004541/zarr/index.json"))
    counts = Counter()
    for record in index["stores"] + index["failures"]:
        path = record["path"]
        if not path.endswith("_eeg.edf"):
            raise ValueError("Expected a source EDF recording")
        url = "https://data.nemar.org/on004541/v1.0.0/" + path.removesuffix("_eeg.edf") + "_events.tsv"
        rows = list(csv.DictReader(io.StringIO(fetch(url).decode("utf-8-sig")), delimiter="\t"))
        categories = Counter(row["trial_type"].strip().lower() for row in rows)
        times = [float(row["onset"]) for row in rows]
        if not times or not np.isfinite(times).all():
            raise ValueError("Missing or non-finite event onset")
        counts["tables"] += 1
        counts["tables_with_both_loc_and_roc"] += int(categories["loc"] > 0 and categories["roc"] > 0)
        counts["tables_with_repeated_loc_or_roc"] += int(max(categories["loc"], categories["roc"]) > 1)
        counts["tables_with_invalid_order"] += int(times != sorted(set(times)) or min(times) < 0)
    assert counts["tables"] == index["discovered_count"]
    return {"source_commit": index["source_commit"], **counts,
            "viewer_conversions": index["store_count"], "viewer_failures": index["failure_count"]}


def main():
    index = json.loads(fetch(INDEX))
    paths = sorted(entry["path"] for entry in index["stores"] if not entry["derived"])
    awake = next(path for path in paths if "_task-awake_acq-EC_eeg.vhdr" in path)
    subject = awake.split("/")[0]
    sedation = next(path for path in paths if path.startswith(subject + "/") and "_task-sed2_acq-rest_" in path)
    results = {"awake": pilot(awake, 30), "pre_awakening": pilot(sedation, 30)}
    assert all(item["source_hz"] == 5000 and item["bytes_read"] <= MAX_BYTES for item in results.values())
    print(json.dumps({"ds005620": {"source_commit": index["source_commit"], **results},
                      "ds004541": event_inventory()}, indent=2))


if __name__ == "__main__":
    main()
