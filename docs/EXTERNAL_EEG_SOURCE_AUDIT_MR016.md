# MR-016.1 — Independent EEG dataset source audit (preliminary, 2026-11-08)

**Status:** PRELIMINARY_SOURCE_AUDIT. No restricted data acquired; no external model validation has been performed. DOSE-I is not re-used as its own independent external set.

Required scientific target: a timestamped behavioral responsiveness probe aligned with pre-decision EEG and dosing events. LOC/ROC labels reflect observed behavioral responses, not a direct measure of subjective consciousness. A dataset with only a binary anesthesia condition or postoperative delirium is **not** equivalent to the 60-second DOSE-I forecast task.

| Candidate | Public evidence | Scientific limitations and next gate |
| --- | --- | --- |
| [Oxford Bench EEG](https://zenodo.org/records/1168447) | Restricted Zenodo 88.3 GB; [16-volunteer 31-channel EEG analysis](https://pmc.ncbi.nlm.nih.gov/articles/PMC7495984/) had behavioral button responses to auditory words around each minute during propofol induction/emergence | Most promising event task, but requires formal access; per-trial event timestamps, dose covariates and reuse rights not yet verified |
| [PhysioNet GABAergic multitaper](https://physionet.org/content/eeg-power-anesthesia/1.0.0/) | Restricted; EEG spectra and responsiveness labels from 10 healthy volunteers plus 44 operating room participants | Spectra rather than necessarily raw EEG; per-probe timelines and equivalence must be validated under DUA |
| [DANDI 001285](https://dandiarchive.org/dandiset/001285) | Open CC-BY-4.0; archive currently reports one subject and one 1.2 GB file, draft | Related ten-volunteer paper does not make this current archive ten subjects; potential pipeline NWB smoke test only, not adequate group-level confirmation |
| [NEMAR / OpenNeuro on004541](https://doi.org/10.82901/nemar.on004541) | Open CC0, 8 people, simultaneous EEG-fNIRS under general anesthesia | Repeated timed behavioral probes are not established. Different endpoint until BIDS events inspected |
| [PhysioNet JSMF ACCESS](https://physionet.org/content/jsmf-access/1.0.0/) | Restricted, 646 surgical patients, derived frontal EEG and postoperative/recovery outcomes, raw EDF request-only | Primary task differs: PACU delirium/emergence, not necessarily repeated timed response probes |

**Recommendation:** request Oxford data access information and a field/event inventory first; review the PhysioNet multitaper DUA and timestamp schema second. An open dataset with all elements required for direct independent DOSE-I validation has **not** been verified. If no legally accessible compatible source exists, record a documented NO-GO or preregister a distinctly different scientific question.

Before any scientific external-validation claim, require independent participants, source license/DUA, timestamp alignment, comparable target, frozen decision cutoff, proper baseline, uncertainty, QC and no post-outcome predictors.

This is public source metadata only, not patient-level content. Further restricted material remains outside GitHub and external model prompts.
