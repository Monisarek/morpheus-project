"""Trailing-window features and independent raw annotation targets."""

from collections import Counter, deque

import numpy as np
from scipy.signal import welch


RATE = 125
WINDOW_S = 30
HORIZON_S = 60
BANDS = {"delta": (0.5, 4), "theta": (4, 8), "alpha": (8, 13),
         "beta": (13, 30), "gamma": (30, 45)}


def window_features(eeg_uv):
    if eeg_uv.shape != (WINDOW_S * RATE, 2):
        return {}, "FAIL", ["incomplete_window"]
    missing = ~np.isfinite(eeg_uv)
    if (missing.mean(axis=0) > 0.05).any():
        return {}, "FAIL", ["missing_above_5pct"]
    if (np.abs(eeg_uv) >= 187.5).any():
        return {}, "FAIL", ["saturation"]
    if (np.nanstd(eeg_uv, axis=0) < 0.1).any():
        return {}, "FAIL", ["flat_channel"]

    reasons = []
    if missing.any():
        eeg_uv = eeg_uv.copy()
        for i in range(2):
            good = np.flatnonzero(~missing[:, i])
            bad = np.flatnonzero(missing[:, i])
            eeg_uv[bad, i] = np.interp(bad, good, eeg_uv[good, i])
        reasons.append("interpolated_at_most_5pct")
    if (np.abs(np.diff(eeg_uv, axis=0)) > 100).any():
        reasons.append("large_sample_jump")

    freq, psd = welch(eeg_uv, fs=RATE, nperseg=500, axis=0)
    mask = (freq >= 0.5) & (freq < 45)
    power = psd[mask].sum(axis=0)
    if (power <= 0).any():
        return {}, "FAIL", ["zero_band_power"]
    for hz in (50, 60):
        line = np.abs(freq - hz) <= 0.5
        if (psd[line].sum(axis=0) > 0.2 * power).any():
            reasons.append(f"line_power_{hz}hz")

    features = {}
    for i in range(2):
        prefix = f"eeg_{i + 1}_"
        relative = psd[mask, i] / power[i]
        cdf = np.cumsum(relative)
        frequencies = freq[mask]
        features[prefix + "median_hz"] = float(np.interp(0.5, cdf, frequencies))
        features[prefix + "edge95_hz"] = float(np.interp(0.95, cdf, frequencies))
        nz = relative[relative > 0]
        features[prefix + "spectral_entropy"] = float(-np.sum(nz * np.log(nz)) / np.log(len(relative)))
        features[prefix + "rms_uv"] = float(np.sqrt(np.mean(eeg_uv[:, i] ** 2)))
        fit = (freq >= 2) & (freq <= 40) & (psd[:, i] > 0)
        if fit.sum() >= 2:
            features[prefix + "log_spectral_slope"] = float(np.polyfit(np.log(freq[fit]), np.log(psd[fit, i]), 1)[0])
        for band, (lo, hi) in BANDS.items():
            value = psd[(freq >= lo) & (freq < hi), i].sum()
            features[prefix + f"abs_{band}"] = float(value * (freq[1] - freq[0]))
            features[prefix + f"rel_{band}"] = float(value / power[i])
    return features, "WARN" if reasons else "PASS", reasons


def build_record(blocks):
    """Retain only two signal blocks and lightweight per-record events/features."""
    trailing = deque(maxlen=2)
    events = []
    rows = []
    doses = deque()
    cumulative = 0.0
    last_dose = None
    end_s = 0.0
    for start_s, end_s, eeg, block_events in blocks:
        trailing.append(eeg)
        for event in block_events:
            events.append(event)
            if event["event_type"] == "Propofol" and event["time_s"] < end_s:
                last_dose = event["time_s"]
                cumulative += event["value"]
                doses.append((last_dose, event["value"]))
        if end_s - start_s < 15 - 1e-8 or len(trailing) < 2:
            continue
        while doses and doses[0][0] < end_s - 60:
            doses.popleft()
        features, qc, reasons = window_features(np.concatenate(trailing))
        rows.append({"time_s": end_s, "elapsed_s": end_s, "dose_mg": cumulative,
                     "dose_60s_mg": sum(dose for _, dose in doses),
                     "dose_age_s": end_s - last_dose if last_dose is not None else None,
                     "qc": qc, "reasons": ";".join(reasons), **features})
    transitions = np.array([e["time_s"] for e in events if e["event_type"] in {"LOC", "ROC"}])
    observations = np.array([e["time_s"] for e in events if e["event_type"] in {"LOC", "ROC", "MOAAS"}])
    audit = Counter()
    for row in rows:
        t = row["time_s"]
        hi = t + HORIZON_S
        reason = ""
        if hi >= end_s:
            reason = "right_censored"
        elif np.searchsorted(observations, hi, side="right") == np.searchsorted(observations, t, side="right"):
            reason = "no_observation_in_horizon"
        row["eligibility"] = reason or "eligible"
        row["target"] = None if reason else int(np.searchsorted(transitions, hi, side="right") >
                                                  np.searchsorted(transitions, t, side="right"))
        audit[row["eligibility"]] += 1
        audit[f"qc_{row['qc']}"] += 1
    return rows, events, dict(audit), end_s


