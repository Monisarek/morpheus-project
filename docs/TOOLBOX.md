# MORPHEUS Tool Library v0.1 — operator guide

This is a deterministic, local CLI catalog. Four tools execute directly. Ten entries document existing `ocon9000` EEG commands without executing them from the catalog. An EEG command's existence in the catalog is not proof the local EEG runtime or input data are available.

## Fast start (PowerShell, repository root)

```powershell
py -m morpheus_tools validate
py -m morpheus_tools list
py -m morpheus_tools find "пустое множество"
py -m morpheus_tools describe dataset.empty-check
py -m morpheus_tools run dataset.profile --input data.csv --max-rows 50000
py -m morpheus_tools run dataset.empty-check --input data.csv --require-column split --expect-subset split=train --expect-subset split=validation
py -m morpheus_tools run log.triage --input run.log
py -m morpheus_tools run artifact.compare --left runs/a --right runs/b
py -m unittest discover -s tests -p test_morpheus_toolbox.py -v
```

Python 3.10+, stdlib-only for CSV/TSV/JSONL/logs/artifact compare; Parquet profiling optionally requires `pyarrow`. This package does not alter DOSE-I/EEG models or write to original datasets.

## Contracts and exit codes

- `0`: check evaluated; for comparison, artifacts match. Does NOT mean independent scientific validation.
- `1`: invalid input / tool error.
- `2`: check failed / artifacts differ.
- `3`: incomplete scan. Never infer that a subset is missing or that a test passed because nothing appeared in sampled rows.

The CLI emits bounded aggregate JSON, never raw participant records, raw log lines, literal subset values or SHA output. It writes detailed **aggregate-only** reports into `.morpheus/tool_runs/`. Column names, filenames and input paths can still be sensitive; review before public use.

## Reuse and caching

Use `find` → `describe` → `run`. Avoid copying large files or reports into model context. The default cache mode is `off`: executes the check again without reusing cached output. Optional `--cache-mode metadata` uses size and timestamp and is **never proof**. Optional `--cache-mode content` reads each byte before returning a content-verified cache hit. A cache hit is not an independent replication; science still requires separate computations and adequate external data when warranted. Full lineage for heavy DAGs belongs in existing DVC/experiment tooling.

## Adding a verified tool

1. Search `morpheus_tools`, `ocon9000` and the local project scripts before implementation.
2. Add exactly one module under `morpheus_tools/tools/` exporting `add_arguments(parser, operation)` and `execute(args, operation)`. Deterministic, read-only by default; no registry-specified subprocess/shell.
3. Register a unique `id`, version, triggers, tested example, input types, risk and limitations in `morpheus_tools/registry.json`.
4. Add happy/negative tests, incomplete-scan and privacy/secret leakage cases, verify Windows compatibility and bounded output.
5. Run `py -m morpheus_tools validate` and `py -m unittest discover -s tests -p test_morpheus_toolbox.py -v`; include a real non-sensitive example and test evidence in a PR.
6. Update the Slack task with short evidence links. No `DONE` until results and real integration are verified. Do not disclose secrets, private/clinical rows, or large raw hashes.

## Existing EEG commands

`py -m morpheus_tools list` shows 10 additional `eeg.*` entries. Those must be run directly through `py -m ocon9000 ...` with a reviewed protocol and verified local state. Particularly `eeg.seal` and `eeg.holdout` require approval. The catalog intentionally refuses to run all `documented_external` commands.

## Limits and deferred work

- Only local read-only tools. This is not a Slack bot or a full autonomous Research Harness.
- JSONL schema is flat dictionaries; no automatic interpretation of nested biomedical records.
- CSV missing values are empty strings and whitespace; other missing-value conventions require protocol-specific changes.
- Subset predicate is literal `column=value`; there is no `eval` or arbitrary code.
- Benchmark actual input/output and repair tokens on equal tasks before claiming savings.
- Do not expand the inventory without a demonstrated repetitive workload.
