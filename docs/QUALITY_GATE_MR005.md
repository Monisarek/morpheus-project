# MR-005 — Scientific and privacy quality gate: acceptance contract

**Status:** SPEC_READY, **NOT IMPLEMENTED**, **NOT VALIDATED**. No agent execution, source data download, or scientific inference is authorized by this document.

This policy is designed to prevent overstated scientific findings, unintended disclosure, temporal and group contamination, and silent data corruption.

## Mandatory input manifest

Each run must declare and freeze experiment/protocol version, source license and data-use approvals, scientific outcome and its ontology, group unit and dataset splits, timestamp / prediction cutoff, allowed feature types, quality selection rules, baseline, evaluation metrics and uncertainty, independence/holdout plan, cost ceiling, resume marker, and independent reviewer. Missing required metadata must yield BLOCKED or explicit UNKNOWN, not a guessed scientific conclusion.

## Synthetic negative tests required before acceptance

| ID | Forbidden condition | Minimum outcome |
| --- | --- | --- |
| G01 | Restricted input without DUA/license proof | BLOCKED_LICENSE |
| G02 | Same subject in train and holdout | BLOCKED_GROUP_LEAKAGE |
| G03 | Renamed/duplicate session crosses partitions | BLOCKED_REVIEW |
| G04 | Predictor timestamp later than decision time | BLOCKED_FUTURE_LEAKAGE |
| G05 | Label or future response used as predictor | BLOCKED_TARGET_LEAKAGE |
| G06 | Preprocessing fitted on holdout | BLOCKED_FIT_LEAKAGE |
| G07 | Negative control performs suspiciously well | BLOCKED_REVIEW |
| G08 | QC selection uses future outcome | BLOCKED_SELECTION_BIAS |
| G09 | Unsynchronized clock axes / bad units of time | BLOCKED_TIME_AXIS |
| G10 | Incompatible scientific dose/unit scale | BLOCKED_UNITS |
| G11 | Patient-level significance inferred from window pseudo-replication | BLOCKED_INFERENCE_UNIT |
| G12 | Confidence interval includes zero, but improvement called proven | BLOCKED_UNSUPPORTED_CLAIM |
| G13 | Multiple hidden test-set peeks and adaptive tuning | BLOCKED_HOLDOUT_REUSE |
| G14 | Missing predeclared scientific comparator | BLOCKED_BASELINE |
| G15 | A partial scan is treated as proof of absence | BLOCKED_INCOMPLETE_SCAN |
| G16 | Raw clinical rows, participant identifiers, secrets in a remote report | BLOCKED_PRIVACY |
| G17 | Clinical input, hidden benchmark key or secrets in public PR/ZIP | BLOCKED_EXPORT |
| G18 | Input/output artifact does not match frozen manifest | BLOCKED_INTEGRITY |
| G19 | DONE without complete reproducible evidence and independent review | BLOCKED_FALSE_DONE |
| G20 | Resume replays already paid computations | BLOCKED_DUPLICATE_RUN |
| G21 | Agent independently certifies itself after reading hidden judge | BLOCKED_NONINDEPENDENT_REVIEW |
| G22 | Unapproved external free-tier transfer of restricted data | BLOCKED_TRANSFER |

Outputs are bounded aggregate rule IDs, counts, completeness indicators and short remediation. Never publish raw SHA collections; only match/no match for manifests.

## Positive controls

- P01: clean legally permitted grouped split with all features at or before cutoff -> VERIFIED_INPUT; this alone is not scientific acceptance.
- P02: a non-significant improvement is reported as inconclusive -> PASS_HONEST_NEGATIVE.
- P03: checkpoint resume reuses finished compute -> PASS_RESUME without duplicate billing.
- P04: aggregate scientific report contains no clinical rows/secrets -> PASS_PRIVACY.
- P05: independent reviewer rejects invalid inference with grounded evidence -> PASS_REJECTION.

## State machine

NEW → PROTOCOL_FROZEN → INPUT_VALIDATED → EXECUTING → QC_REVIEW → SCIENCE_REVIEW → ACCEPTED / REJECTED / INDETERMINATE. Intermediate BLOCKED, WAITING_QUOTA and WAITING_ACCESS states preserve source evidence. A failed hypothesis is a scientific result only when the experiment is valid; an invalid experiment is not a discovery.

**Definition of DONE:** 22/22 negative scenarios correctly refuse or request human review, 5/5 positive controls behave as designed, and one permissioned end-to-end research pipeline run is inspected by an independent reviewer. A prose checklist does not satisfy these gates.

Private implementation notes and ownership are tracked in MORPHEUS Slack task MR-005. No raw EEG data is included in this document.
