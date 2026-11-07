"""Bounded streaming reader for the published DOSE-I v2 raw archive."""

import ast
import csv
import hashlib
from io import TextIOWrapper
from itertools import islice
from pathlib import PurePosixPath
import re
from zipfile import ZipFile

import numpy as np


RAW_MD5 = "b98c8a81d2e866085f9e7ac75a950754"
METADATA_MD5 = "5c6292ff0bbb9bc92c92dc3aec44bf25"
GRID_HZ = 250
SAMPLE_RATE = 125
BLOCK_SECONDS = 15
CHANNELS = ("Intellivue/EEG_1", "Intellivue/EEG_2")
EVENT_COLUMNS = ("SOC", "MOAAS", "Propofol", "Endoscopy", "Midazolam", "Misc")
UNITS_TO_UV = {"uV": 1.0, "µV": 1.0, "μV": 1.0, "V": 1e6}
RECORD_NAME = re.compile(r"10[-_](\d{3})\.csv", re.ASCII)


def _members(archive):
    members = {}
    for item in archive.infolist():
        match = RECORD_NAME.fullmatch(PurePosixPath(item.filename).name)
        if match is not None and not item.is_dir():
            record_id = f"10-{match[1]}"
            if record_id in members:
                raise ValueError(f"duplicate record ID in DOSE-I archive: {record_id}")
            members[record_id] = item
    if not members:
        raise ValueError("no raw DOSE-I record members in archive")
    return members


def _verify(path, expected_md5, kind):
    digest = hashlib.md5(usedforsecurity=False)
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected_md5:
        raise ValueError(f"archive does not match the published DOSE-I v2 {kind} MD5")


def recordings(path, verify=True):
    if verify:
        _verify(path, RAW_MD5, "raw")
    with ZipFile(path) as archive:
        return sorted(_members(archive))


def metadata(path, allowed_ids):
    """Read published QC fields for the selected partition only."""
    _verify(path, METADATA_MD5, "metadata")
    rows = {}
    numeric = ("length", "SOC_trans", "MOAAS_sum")
    with ZipFile(path) as archive, archive.open("metadata/DOSE-I_metadata.csv") as binary:
        with TextIOWrapper(binary, encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream, strict=True)
            required = {"", "version", "residual_errors", *numeric}
            if not reader.fieldnames or not required.issubset(reader.fieldnames):
                raise ValueError("missing DOSE-I metadata columns")
            for row in reader:
                record_id = f"10-{int(row['']):03d}"
                if record_id not in allowed_ids:
                    continue
                if record_id in rows:
                    raise ValueError(f"duplicate DOSE-I metadata for {record_id}")
                errors = ast.literal_eval(row["residual_errors"] or "[]")
                if not isinstance(errors, list) or not all(isinstance(error, str) for error in errors):
                    raise ValueError(f"invalid DOSE-I residual errors for {record_id}")
                rows[record_id] = {**{name: int(row[name]) for name in numeric},
                                   "residual_errors": errors, "version": row["version"]}
    if set(rows) != allowed_ids:
        raise ValueError("DOSE-I metadata is missing an allowed recording")
    return rows


def profile(record_id):
    return {
        "dataset_id": "DOSE-I", "dataset_version": "v2",
        "source_record_id": record_id, "session_id": record_id, "subject_id": "UNKNOWN",
        "format": "DOSE-I raw CSV in ZIP", "protocol": "procedural sedation for endoscopy",
        "drug_in_protocol": "propofol", "sample_rate": SAMPLE_RATE,
        "timestamp_grid_hz": GRID_HZ, "time_origin": "first raw row", "timezone": "UNKNOWN",
        "timestamp_resolution_s": 0.004, "clinical_timing_uncertainty_s": "UNKNOWN",
        "channels": list(CHANNELS), "units": "uV", "reference": "bipolar",
        "protocol_montage": "Fp2–Fp1 and Fz–F7, mirrored for left-handed participants",
        "record_montage": "UNKNOWN", "device": "Philips IntelliVue MP40", "filters": "UNKNOWN",
        "phase": "UNKNOWN", "label_source": "DOSE-I raw clinical annotations SOC and MOAAS",
    }


def _schema(header):
    if header is None or len(set(header)) != len(header):
        raise ValueError("missing or duplicated DOSE-I CSV header")
    columns = {name: index for index, name in enumerate(header)}
    required = {"Time", "SOC", "MOAAS", "Propofol"}
    if not required.issubset(columns):
        raise ValueError("missing DOSE-I columns: " + ", ".join(sorted(required - columns.keys())))
    channels = []
    for channel in CHANNELS:
        options = {channel: 1.0}
        options.update({f"{channel}-{unit}": scale for unit, scale in UNITS_TO_UV.items()})
        matches = [(columns[name], scale) for name, scale in options.items() if name in columns]
        if len(matches) != 1:
            raise ValueError(f"missing channel or ambiguous EEG units for {channel}")
        channels.append(matches[0])
    return columns, channels


def _event(column, text, time_s):
    if column == "Misc":
        value = text
    else:
        value = float(text)
        if not np.isfinite(value):
            raise ValueError(f"nonfinite {column} at {time_s:g} s")
        if column in ("SOC", "Endoscopy") and value not in (0, 1):
            raise ValueError(f"invalid {column} code at {time_s:g} s")
        if column == "MOAAS" and value not in (1, 2, 3, 4, 5):
            raise ValueError(f"invalid MOAAS score at {time_s:g} s")
        if column in ("Propofol", "Midazolam") and value <= 0:
            raise ValueError(f"invalid {column} dose at {time_s:g} s")
    event_type = {0: "LOC", 1: "ROC"}[value] if column == "SOC" else column
    return {"time_s": time_s, "event_type": event_type, "value": value, "label_source": f"raw/{column}"}


def _eeg(rows, channels):
    eeg = np.empty(((len(rows) + 1) // 2, len(channels)))
    for channel, (column, scale) in enumerate(channels):
        raw = np.asarray([row[column] or "nan" for row in rows], dtype=float) * scale
        if np.isinf(raw).any():
            raise ValueError("nonfinite EEG sample")
        even = raw[::2]
        odd = raw[1::2]
        paired = even[:len(odd)]
        # Retain a clipped value even if a duplicate earlier row would hide saturation.
        eeg[:len(odd), channel] = np.where(np.isnan(paired) | (np.abs(odd) >= 187.5), odd, paired)
        if len(even) > len(odd):
            eeg[-1, channel] = even[-1]
    return eeg


def blocks(path, record_id):
    """Yield (start_s, end_s, EEG samples in µV, events) in 15 s blocks."""
    with ZipFile(path) as archive:
        member = _members(archive).get(record_id)
        if member is None:
            raise ValueError(f"missing raw recording: {record_id}")
        with archive.open(member) as binary, TextIOWrapper(binary, encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream, strict=True)
            header = next(reader, None)
            columns, channels = _schema(header)
            event_columns = [(name, columns[name]) for name in EVENT_COLUMNS if name in columns]
            offset = 0
            origin_ns = None
            time_column = columns["Time"]
            while rows := list(islice(reader, BLOCK_SECONDS * GRID_HZ)):
                if any(len(row) != len(header) for row in rows):
                    raise ValueError(f"ragged DOSE-I CSV row after {offset / GRID_HZ:g} s")
                times = np.asarray([row[time_column] for row in rows], dtype="datetime64[ns]")
                if np.isnat(times).any():
                    raise ValueError("missing timestamp in DOSE-I CSV")
                nanoseconds = times.astype(np.int64)
                if origin_ns is None:
                    origin_ns = int(nanoseconds[0])
                if np.any(nanoseconds - origin_ns != 4_000_000 * np.arange(offset, offset + len(rows))):
                    raise ValueError(f"DOSE-I time grid gap, duplicate or reversal after {offset / GRID_HZ:g} s")
                events = [
                    _event(name, row[index], (offset + index_in_block) / GRID_HZ)
                    for index_in_block, row in enumerate(rows)
                    for name, index in event_columns
                    if row[index]
                ]
                yield offset / GRID_HZ, (offset + len(rows)) / GRID_HZ, _eeg(rows, channels), events
                offset += len(rows)
            if not offset:
                raise ValueError("empty DOSE-I record")
