# MORPHEUS — operational state (verified 2026-11-08)

> **Dated snapshot, not a live feed.** Always recheck the current GitHub PR/issues/CI and authorized Slack task registry. Public-safe only; no raw EEG, patient identifiers, secret URLs or DUA-only materials.

## Start here
1. Read root [AGENTS.md](../AGENTS.md) before any Codex task.
2. Read this public-safe status and [STRATEGY.md](../STRATEGY.md) if present; otherwise inspect the current strategy PR #4 merge and strategy document in repo.
3. Verify live [issues](https://github.com/Monisarek/morpheus-project/issues) and [pull requests](https://github.com/Monisarek/morpheus-project/pulls) before using this snapshot.
4. For private task state, use the authorized MORPHEUS Slack List. For broader private context, use separately restricted MORPHEUS memory/Drive, never pull private content into a public GitHub PR.
5. Do not change a local EEG-003 worktree without a read-only inventory; no force/reset/checkout of unfinished work.

## Science — no false readiness claims
- **EEG-001:** DOSE-I prediction of behavioral LOC/ROC response, **not a direct measurement of consciousness**. Original comparison EEG+context vs time/dose AP improvement +0.078 (95% CI +0.020…+0.135). Internal repeat verified 16 artifacts in EEG-002.
- **EEG-002:** after including prior clinical responsiveness in the baseline, EEG incremental AP is **+0.017 (95% CI −0.002…+0.039)** on 9,962 QC-eligible windows from 168 records. CI crosses zero; previous holdout reused; group unit is recording, not verified unique person; no external confirmation. [PR #1](https://github.com/Monisarek/morpheus-project/pull/1) stays **OPEN for scientific review**, not silently abandoned or approved.
- **EEG-003 / E25:** according to the local Codex report, a private reviewer packet and local checkpoint inventory were assembled; source artifacts not independently examined through GitHub. H03/H03-B protocol/rights/method issues remain. **E25 OPEN, restricted real-data runs NO-GO.** See [Issue #9](https://github.com/Monisarek/morpheus-project/issues/9). No rerun of E20/E21 or re-opening held-out data.
- External compatible EEG data access and timed labels remain unproven; unrelated anesthesia datasets are not an external confirmation.

## Code / PR state
- **Merged 2026-11-08:** [#2 Tool Library](https://github.com/Monisarek/morpheus-project/pull/2) → [#8 MR-005 synthetic gate](https://github.com/Monisarek/morpheus-project/pull/8), then [#3 blind evaluation protocol](https://github.com/Monisarek/morpheus-project/pull/3), [#4 strategy](https://github.com/Monisarek/morpheus-project/pull/4), [#5 quality/source audit docs](https://github.com/Monisarek/morpheus-project/pull/5). PR #8 was originally stacked on #2 and deliberately retargeted to main after #2 merge.
- Tool Library: `py -m morpheus_tools find/describe/run`, 14 tool records (4 executable, 10 documentation-only `ocon9000`). Reported Windows QA 21/21 unit + 25/25 CLI and GitHub Python 3.10–3.12 CI. Token savings not measured; no independent clinical validation.
- MR-005: GitHub synthetic test suite 57/57, Docker E23 reported 8 synthetic isolation probes PASS_SYNTHETIC_ONLY; the scientific E25 gate is **not passed**.
- [Issue #10 — Scientific Discovery/MR-021.3](https://github.com/Monisarek/morpheus-project/issues/10) is **OPEN / TODO**, specifying official read-only science APIs/MCP, literature and data-rights checks before experiments. No source integration or new experimental result is claimed.

## Runtime / task discipline
- Slack Socket Mode Dispatcher v3.3 was reported working with `ping`, `task`, `queue`, `status`, SQLite and Windows Task Scheduler. It is a task interface/queue, **not yet an approved autonomous research executor**. Agent auto-execution is OFF; authenticated execution, isolation, full Slack→PR/Drive→Slack reporting and actual logout/login reliability are incomplete.
- Research Harness MR-004 still IN_PROGRESS; quota-aware resume MR-006 TODO; scientific gate MR-005 REVIEW; independent models exam not completed. Cap concurrent WIP to one scientific question + one necessary engineering blocker.
- Scientific workflow: question → prior literature/alternatives → dataset license/DUA & QC → preregistered baseline/negative controls → restricted execution only after gate → interpretation/uncertainty → independent review → record (including NO-GO).
- No raw clinical/participant rows, secrets, restricted documents, personal files or large logs in this repository, Slack or external LLM. No unauthorized paid API/fallback, no arbitrary Slack command execution.

## What to do next
1. EEG-003 E25: obtain independent scientific reviewer and authorized data controller verdict on protocol, DUA, privacy, split, leakage and uncertainty; continue **NO-GO** unless independently cleared.
2. MR-006: implement and test resumable idempotent stages on synthetic fixtures, not restricted EEG inputs.
3. MR-004/014/015: complete a reproducible scientific flow with negative controls and provenance, then qualify agents by blind exam.
4. MR-021.3: add limited research discovery in existing Tool Library. Do not block critical repairs with an unrelated new orchestration stack.

## Cross-system references
Research code and evidence: https://github.com/Monisarek/morpheus-project
Scientific review: https://github.com/Monisarek/morpheus-project/issues/9
Scientific sources integration: https://github.com/Monisarek/morpheus-project/issues/10
Operational task authority: restricted MORPHEUS Slack List (no live public export).
Canonical broader handoff: restricted MORPHEUS Drive/memory, not readable to the public.

**Evidence rule:** `DONE` requires actual acceptance evidence; merged code, synthetic tests, locally asserted packets or a cached run alone do not pass scientific/clinical gates.
