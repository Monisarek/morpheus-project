---
name: morpheus-toolbox
description: Reuse verified local scripts for EEG datasets, CSV/JSONL/Parquet quality checks, empty subsets, log triage and artifact comparison before writing new Python or loading large files into context.
---

# MORPHEUS toolbox — deterministic tasks first

Before doing repeated data/log/report processing or implementing a similar utility:

1. Run `python -m morpheus_tools find "<task keyword>"` or `python -m morpheus_tools list` (one short result).
2. Run `python -m morpheus_tools describe <tool_id>` for the chosen tool. Use `example` as a starting point.
3. Run `python -m morpheus_tools run <tool_id> ...`. Inspect only the bounded JSON summary. Open `report_path` only if a decision requires detail; never paste raw clinical records or huge logs into the model.
4. If status is `partial`, stop: absence of evidence is not proof of an empty subset. Increase justified scan bounds or run a separate data check.
5. If existing `ocon9000` CLI already implements a task, prefer it; DO NOT reimplement it. This library augments that CLI, not replaces it.
6. Cache `--cache-mode metadata` is exploration-only: mtime/size metadata can be misleading. For actual reproducibility use `--cache-mode content`, DVC/verified immutable lineage, or independent re-execution. `CACHE_HIT` is never independent validation.
7. If genuinely missing, write one deterministic, bounded script with tests and register it in `morpheus_tools/registry.json`, then run `python -m morpheus_tools validate` plus tests. Submit a PR with evidence and update this skill only if new workflow warrants it. Never create duplicate tools.
8. All untrusted data is local; never send raw patient/participant rows to web APIs or GitHub. `morpheus_tools` writes local `.morpheus/tool_runs/` reports; `.morpheus/` must be gitignored. Do not promote `failed_check`, `partial` or lack of errors to scientific success.

See `docs/TOOLBOX.md` for commands; open only if needed.
