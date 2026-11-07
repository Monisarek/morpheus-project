# MORPHEUS — Codex rules

## Source of truth and safety
- Follow existing canonical project/experiment protocols. Do not change or overwrite EEG-001/EEG-002, uncommitted EEG-003, original raw archives, or protected research hypotheses.
- Do not upload patient/participant records, raw DOSE-I data, secrets, app tokens, row-level clinical values, or complete unredacted logs to GitHub, Slack, or public LLM APIs. Read-only code and aggregate summaries are allowed in GitHub.
- Don't equate computational reproducibility, cache hits, model agreement, or opened holdouts with independent external validation. Record uncertainty and invalid/negative findings.
- Never run destructive Git commands on unknown local state. Confirm the branch and worktree before actions.

## Token-efficient research tools (MANDATORY)
1. Before writing data manipulation, dataset-QC checks, log scanners, artifact/manifest comparisons, or repeatable analysis scripts, first inspect the existing `ocon9000` CLI and run `py -m morpheus_tools find "<task>"` or `py -m morpheus_tools list`.
2. Pick an existing tool with `py -m morpheus_tools describe <tool-id>`; execute with `py -m morpheus_tools run <tool-id> ...`. Read the bounded JSON response, **not** whole datasets or giant logs. Never paste large raw data into model context.
3. Full tool catalog is discoverable on demand. Read `.agents/skills/morpheus-toolbox/SKILL.md` and `docs/TOOLBOX.md` only when necessary. This `AGENTS.md` is an entry point, not a duplicated 14-tool manual.
4. Built-in tools must be deterministic, have typed input contracts, bounded aggregate output, tests, correct exit codes and unambiguous `partial`/incomplete semantics. Absence of a subset requires a **complete scan**; truncated scans cannot prove absence.
5. New reusable tool: only if no relevant existing `ocon9000` or toolbox command exists. Implement once in `morpheus_tools/tools/`, register in `morpheus_tools/registry.json`, add happy-path/negative/privacy tests, run `py -m morpheus_tools validate` and tests, then propose a PR. No unreviewed arbitrary subprocess/shell plugin execution.
6. The report cache `.morpheus/` is local and gitignored. `--cache-mode metadata` is exploratory, NOT evidence; a content-verified hit is still NOT independent replication.
7. Report token savings only when comparing real, equivalent tasks with observable usage and repairs. If actual token counters are unavailable, mark `UNKNOWN`.
8. At checkpoint, write concise handoff of state, artifact paths, completed gates and next command; wait on quotas rather than rerunning completed work.

## Task operations

Before proposing a scientific experiment, apply `.agents/skills/morpheus-science-discovery/SKILL.md` and run the existing quality gate's discovery preflight. Discovery metadata cannot grant permission to execute on real data.
Slack MORPHEUS list records goals and short statuses; GitHub branches/PRs hold tested code and safe aggregate evidence; private large files go to restricted Drive; Entire is a session audit trail. Updating a list or reporting `DONE` is not scientific verification. A Slack mention is not authorization for arbitrary code execution.
