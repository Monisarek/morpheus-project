# MORPHEUS RESEARCH BIOENGINEERING — Research strategy (2026–2027)

> **Status:** strategy proposal. This is research governance, not proof that a laboratory or scientific discovery exists. No secrets, private personal finances, raw clinical data or hidden evaluation answers belong in this repository.

## Purpose and north star

MORPHEUS will develop a **small, reproducible, agent-assisted scientific research environment**. Its value is the ability to formulate falsifiable questions, document protocols before inference, execute legally permissible computations, catch invalid findings, and obtain independently reviewable results — including negative results. Later, a scientifically justified hypothesis may be tested using an existing qualified physical laboratory.

**North-star measure:** number of independently reviewable completed research cycles per verifiable cost. Secondary: independent rerun success, uncertainty reporting, blocked leakage/privacy violations, and measured cost per verified outcome. The number of agents, code commits, model tokens, experiments attempted and mutually agreeable LLM replies are **not** success measures.

### Scope and non-goals

- **In scope:** research questions, source licenses, data lineage, QC and statistical validity, agent qualification, verified computational results, cost/quotas and safety, scientific partnerships.
- **Not in scope:** personal finance, salary, family resources, job search, personal financial data, medical advice, clinical efficacy claims, unregulated biological work.
- **Not now:** buying lab instruments, renting premises, hiring lab staff, allowing uncontrolled autonomous experiments, using paid cloud GPU jobs by default or inventing scientific discoveries.
- Budget is **zero new paid services unless explicitly approved**. Official free quotas and selective grants must be documented individually in MR-025 before use. No raw clinical rows or secrets in free-tier hosted LLM prompts.

## Stage gates and dependencies

| Gate | Outcome | Tasks | Evidence before advance |
| --- | --- | --- | --- |
| 0 — Preserve current work | Recover stalled EEG-003 without destroying state; test reusable tools in isolated worktree | MR-003, MR-021.1, MR-020, MR-025 | Inventory and checkpoint, unchanged local research data, bounded costs; no `git reset --hard`/unreviewed checkout |
| 1 — Verify scientific harness | A guarded workflow with reproducibility, negative tests and quota-safe resume | MR-004, MR-005, MR-006, MR-014, MR-015, MR-019 | Registered protocol, legal inputs, participant/time leakage gates, at least two end-to-end cycles including a deliberately negative/blocked result, independent code/method audit, checkpoint/resume and bounded spending |
| 2 — Qualify models | Decide what tasks each candidate agent may perform | MR-007–MR-012 | Identical safe tasks for Codex, Gemini, Groq; isolated contexts; frozen submissions *before* evaluator access; verified code/metrics, actual token/time costs and scientific objections |
| 3 — Demonstrate new science | Check transferability to a new non-clinical domain, without overclaiming | MR-016, MR-022 | Attempt scientifically comparable external EEG validation (or documented blocker) and one prospective chemistry/material-science hypothesis on licensed data with simple baselines, negative controls and held-out evaluation |
| 4 — Validate external relevance | Scientific partner feasibility and transparent results | MR-023, MR-024 | Qualified external laboratory reviews a safe standard measurement; costs/rights/QC defined; one honest public reproducible case and documented demand interviews |
| 5 — Optional commercial laboratory | Only if evidence supports a business | MR-017 | Legal permissions, qualified staff, real verified demand, pilot data and dedicated approved budget. Otherwise remain ON_HOLD |

**No shortcut:** Slack bot online, Python unit tests, agreement between LLMs or a high synthetic benchmark score do not authorize claims of scientific readiness. MORPHEUS must recognize NO-GO when inputs, protocol, uncertainty, access, independence or expert oversight are insufficient.

## Operating cadence

1. **NOW:** one scientific question and at most one essential engineering blocker; preserve EEG-003 state, scientific quality gate, quota/resume, and cost boundaries. Do not silently add side projects.
2. **NEXT:** complete the scientific pipeline's explicit acceptance tests; then independent agent benchmark. Claim/check free inference quotas before benchmark runs, not after they expire.
3. **LATER:** independent EEG replication; first well-defined computational chemistry/materials pilot; optional external physical measurement and non-clinical portfolio.
4. **ON HOLD:** commercial wet-lab ownership, hardware purchases, paid inference and speculative features without a measured blocker.

New ideas must answer: **Which stage gate does this close? What verified artifact will exist? What does it replace in NOW? What budget/risk does it require? Can we reuse a tested tool?** If unclear, park the idea. A negative result advances scientific knowledge only when the experimental process itself is valid.

## Scientific and operational controls

- Freeze protocol, data access and unit of independence before seeing final results. Distinguish LOC/ROC behavioral responsiveness from consciousness.
- Separate public reproducible source/aggregate metrics in GitHub from restricted input data, approvals, keys and larger artifacts in private storage. Never publish raw clinical rows, private files or hidden benchmark evaluator fixtures.
- Scientific reviewers and method validators have independent authority to block claims or releases. A model's assertion is not proof.
- Use deterministic tools before authoring more code: `python -m morpheus_tools find` → `describe` → `run`. A cache hit is not independent replication.
- Enforce `WAITING_QUOTA` with exact checkpoint/resume command and no repeated costly steps.
- Each task: `STATUS / VERIFIED COMPLETION / SCIENTIFIC CONCLUSION OR UNKNOWN / EVIDENCE / REAL COST OR UNKNOWN / BLOCKER / NEXT`.
- Public GitHub Actions: small, time-bounded, standard-runner tests only. Do not use paid larger runners or public self-hosted runner from a clinical research PC.

## Governance and records

- **Slack MORPHEUS List:** operational task states, owners, acceptance, report links.
- **GitHub:** versioned safe research protocols/code, PR review, aggregated results, tested artifacts.
- **Restricted Drive:** private scientific strategy, controlled documents, raw large files when lawful. Hidden model evaluation answer keys **must not** be shared with tested model contexts or added to public branches.
- **Separate personal project:** personal finances, income, career and life expenses are not MORPHEUS tasks. MR-020 is **MORPHEUS research budget** only; MR-025 is **provider grants/free API quotas** only.

The complete private strategy and implementation plan is held in the MORPHEUS Drive workspace. The first session after quota restoration begins with MR-003 checkpoint/inventory, MR-021.1 safe tool validation, MR-006 resume mechanics, then MR-005 scientific/privacy negative cases. Only after passing gates should the system run large new experiments.
