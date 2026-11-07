# MR-005 synthetic scientific and privacy gates

[Issue #7](https://github.com/Monisarek/morpheus-project/issues/7) · [Acceptance contract in draft PR #5](https://github.com/Monisarek/morpheus-project/pull/5)

This implementation evaluates synthetic evidence. A `VERIFIED_INPUT` verdict means the supplied fixture satisfies the input predicates. Scientific acceptance and E25 require an independent reviewer and an authorized end-to-end pipeline.

## Run

```powershell
py -m morpheus_tools validate
py -m unittest discover -s tests -p 'test_morpheus*.py' -v
New-Item -ItemType Directory -Force .morpheus | Out-Null
py -c "import json,sys; sys.path.insert(0,'tests'); from test_morpheus_quality_gate import valid_manifest; print(json.dumps(valid_manifest()))" |
    Set-Content -Encoding utf8 .morpheus/mr005-synthetic.json
py -m morpheus_tools.quality_gate .morpheus/mr005-synthetic.json
```

The runnable example is `valid_manifest()` in `tests/test_morpheus_quality_gate.py`. It combines the science and execution fixtures used by the tests. JSON must have unique keys, finite numbers, schema version 1, and scope `synthetic`. It is limited to 256 KiB. The evaluator requires a declared protocol, including the feature scope, comparator, uncertainty, cutoff, holdout and review plans, resume marker, and zero paid budget.

| Exit | Meaning |
| --- | --- |
| 0 | Complete synthetic manifest passes the input checks |
| 1 | Malformed or unreadable manifest |
| 2 | One or more gates block the fixture, or ambiguous or missing evidence needs review |

Output consists of status, gate/control IDs, counts, and fixed remediation. Scientific values, private paths, hashes, identities and supplied error strings are kept out of stdout. Toolbox's registry remains at 14 entries. The tests reuse `dataset.empty-check` and `artifact.compare` for the bounded scan and frozen artifact comparison evidence. The Windows suite ran 57 tests including all 22 required negative cases and five positive controls.

## Evidence boundary

The checks evaluate the structure and consistency of supplied evidence. A real deployment still needs trusted data admission, independent evidence collection and review, and a release gate. A synthetic report with plausible-looking classifications, approval references, signatures or reviewer IDs cannot establish those facts. Humans must establish DUA applicability, subject/session identity, clock synchronization, dose semantics, scientific comparability, suspicious-control thresholds, claim validity and reviewer independence. The gate has no scheduler, network client, publisher or authority to issue DONE for a scientific experiment.

E23 is tracked separately as a Docker canary. Any successful canary is scoped to the tested image, process, binds, namespace and denied operations. E25 remains open.
