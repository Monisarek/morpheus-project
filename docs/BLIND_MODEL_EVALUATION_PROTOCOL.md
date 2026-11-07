# MORPHEUS — MR-007 independent blind model evaluation

**Status:** protocol and synthetic benchmark artifacts prepared locally; no external model run yet. This file deliberately contains **NO** hidden answers, fixture generation seeds, reference code, or private scorer.

## Objective

Compare the ability of Codex, Gemini, and GPT-OSS/Groq to produce reproducible, scientifically sound *engineering checks* on equivalent synthetic research data, then evaluate total observed cost-to-verified-result. Historic EEG-001/002 conclusions are published and may not qualify as truly unknown test answers.

## Scope (three fixed tasks)

1. Group-level train/validation/test contamination: participants spanning more than one partition.
2. Predictive temporal leakage: features unavailable at decision time.
3. Average precision improvement with paired participant-level bootstrap uncertainty, including ties and conclusion discipline.

Input data is entirely synthetic and safe to share. These tasks test scientific data engineering, **not** independent discovery of new biological mechanisms or clinical efficacy.

## Strict separation

- The **agent packet** (same bytes to every candidate) contains only input CSVs, task instructions and output contract.
- The **private evaluator** contains deterministic expected values, input integrity manifest, scoring algorithm and tests. Store away from all agents, repository checkouts, connected model contexts, and publicly linked Drive documents. **Never commit it to GitHub.**
- Use fresh isolated agent sessions with no access to the other agents' logs, previous MORPHEUS EEG reports, hidden results or evaluator.
- No candidate should receive a privileged run, hidden hints or different repair opportunity. Give identical environment constraints and duration, or explicitly label the results not directly comparable.
- Finalize and freeze the first complete code + machine-readable results + method notes from all candidates *before* opening any hidden keys. Never score a revised attempt on the same sealed packet as independent blind evidence.

## Objective scoring and research gates

- Machine grade: 21 numerical/structured fields across three cases; field-level pass/fail only, no raw expected answers in feedback; reject changed input data.
- Independent execution: before running untrusted agent scripts, audit them and run in network-disabled, secret-free sandbox. Confirm the script computes outputs from input, rather than embedding known answers.
- Scientific audit: verify grouping, chronology, uncertainty, limitations, correctness of negative and indeterminate conclusions. Numeric match by itself is not scientific validity.
- Record attempts, provider, exact model/version, scope, runtime, API calls, repair calls, observed input/output/cached tokens and real cost. Use **UNKNOWN** for unavailable counters; do not invent savings.
- Compare cost-to-*verified*-result only after the scientific and reproducibility gates. Agreement among LLMs is not a substitute for ground truth.
- Cross-review/Clash (MR-012) happens only after frozen submissions and first-pass scoring; record changed decisions separately.

## Current acceptance status

| Gate | Evidence | Status |
| --- | --- | --- |
| Synthetic preparation | Three generated CSV task families | PREPARED |
| Private evaluator separated | Distinct agent/private archives; not stored in Git | PREPARED |
| Offline tests | 13 unittest cases passed in independent environment | PASS_LOCAL |
| Codex independent run | Await available quota and isolated execution | BLOCKED |
| Gemini independent run | Await provider/tool access, fixed conditions | BLOCKED |
| GPT-OSS/Groq independent run | Await provider/tool access, fixed conditions | BLOCKED |
| Scientific audit & cost comparison | No frozen submissions yet | NOT_STARTED |
| Cross-critique | Do not start before first-pass grade | NOT_STARTED |

## Logistics and security

The agent packet and private evaluator are held **outside** this public repository. They should not be uploaded to a shared model-accessible root. No clinical records, access tokens or sensitive EEG archives may enter free-tier external model prompts. GitHub Actions should not execute the private evaluator or consume model inference credits.

Formal project backlog: **MR-007** (preparation) → **MR-008/009/010** (independent model runs) → **MR-011** (blind grading) → **MR-012** (cross-critique). Safe scientific methods and source/experiment protections remain governed by each experiment's protocol.

## Limitations

Synthetic checks establish a controlled first-level capability examination only. Broader agent qualification requires fresh unexposed research questions, legally accessible datasets, independent replication, negative controls, and scientific reviewers. The private evaluation pack must remain sealed until candidates are frozen.
