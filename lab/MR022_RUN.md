# MR-022 AqSolDB V1

The frozen protocol is in [aqsol-solubility-v1.json](protocols/aqsol-solubility-v1.json). This is a public nonclinical benchmark on heterogeneous deposited measurements. The eligible population excludes ambiguous stereochemistry as well as salts, mixtures, acyclic structures and duplicate canonical identities.

A short initializer changes ownership only on the dedicated Docker volume. The scientific phases mount dependencies read-only.

## Reproduction

Retrieve only the official original CSV linked in the protocol and place it at `.morpheus/aqsol-v1/original.csv`. The Dataverse V1 metadata identifies file `3407241`, its original size and MD5. `prepare` and `preflight` verify those values and the frozen SHA-256. Raw data, per-row predictions and checkpoints remain local. [Dataverse deposit](https://doi.org/10.7910/DVN/OVHAW8) · [Data descriptor](https://pmc.ncbi.nlm.nih.gov/articles/PMC6687799/)

Use the pinned local Docker image in the protocol. Place the Linux amd64 CPython 3.12 wheels for `aqsol-requirements.txt` in `.morpheus/aqsol-v1/wheels`. `setup` installs as the unprivileged user into a dedicated local Docker dependency volume with networking disabled and enforces the wheel hashes in `aqsol-linux-amd64.lock`.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File lab/aqsol_docker.ps1 -Phase setup
powershell -NoProfile -ExecutionPolicy Bypass -File lab/aqsol_docker.ps1 -Phase test
powershell -NoProfile -ExecutionPolicy Bypass -File lab/aqsol_docker.ps1 -Phase prepare
powershell -NoProfile -ExecutionPolicy Bypass -File lab/aqsol_docker.ps1 -Phase preflight
powershell -NoProfile -ExecutionPolicy Bypass -File lab/aqsol_docker.ps1 -Phase run
```

`prepare` computes source and membership facts without fitting a model. For a new authorized run, commit the emitted aggregate freeze and pass the separate MR-005 checks before `run`. The existing MR-005 synthetic tests establish engineering coverage. The source-specific preflight and Lyra's scoped conditional authorization govern this public trial. The clinical gate and Iris-only Dispatcher retain their existing scope.

`run` requires the committed freeze and admission record, verifies the source, environment and prepared partition again, then uses the existing MR-006 stages. Repeating it against the same local checkpoint reuses verified results. A fresh `prepare` requires a fresh private state directory. Keep the same seed and protocol when verifying reproduction.

## V1 preflight outcome

The fixed split was rejected before fitting. It allocated 2,095 of 4,779 eligible rows (43.84%) to holdout, above the prespecified 25% ceiling. The cohort met its minimums with 1,186 scaffolds. The existing MR-005 synthetic checks passed. Admission for the actual V1 split remains blocked. No model, negative-control fits or held-out metrics were produced. A change to the split procedure requires a new reviewed protocol version. [Preflight evidence](evidence/aqsol-v1-preflight-blocked.json)
