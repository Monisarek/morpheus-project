# MR-022 AqSolDB V1

The frozen protocol is in [aqsol-solubility-v1.json](protocols/aqsol-solubility-v1.json). This is a public nonclinical benchmark on heterogeneous deposited measurements. The eligible population excludes ambiguous stereochemistry as well as salts, mixtures, acyclic structures and duplicate canonical identities.

## Reproduction

Retrieve only the official original CSV linked in the protocol and place it at `.morpheus/aqsol-v1/original.csv`. The Dataverse V1 metadata identifies file `3407241`, its original size and MD5. `prepare` and `preflight` verify those values and the frozen SHA-256. Raw data, per-row predictions and checkpoints remain local. [Dataverse deposit](https://doi.org/10.7910/DVN/OVHAW8) · [Data descriptor](https://pmc.ncbi.nlm.nih.gov/articles/PMC6687799/)

Use the pinned local Docker image in the protocol. Place the Linux amd64 CPython 3.12 wheels for `aqsol-requirements.txt` in `.morpheus/aqsol-v1/wheels`. `setup` installs into a dedicated local folder with networking disabled and enforces the wheel hashes in `aqsol-linux-amd64.lock`.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File lab/aqsol_docker.ps1 -Phase setup
powershell -NoProfile -ExecutionPolicy Bypass -File lab/aqsol_docker.ps1 -Phase test
powershell -NoProfile -ExecutionPolicy Bypass -File lab/aqsol_docker.ps1 -Phase prepare
powershell -NoProfile -ExecutionPolicy Bypass -File lab/aqsol_docker.ps1 -Phase preflight
powershell -NoProfile -ExecutionPolicy Bypass -File lab/aqsol_docker.ps1 -Phase run
```

`prepare` computes source and membership facts without fitting a model. For a new authorized run, commit the emitted aggregate freeze and pass the separate MR-005 checks before `run`. The existing MR-005 synthetic tests establish engineering coverage. The source-specific preflight and Lyra's scoped conditional authorization govern this public trial. The clinical gate and Iris-only Dispatcher retain their existing scope.

`run` requires the committed freeze and admission record, verifies the source, environment and prepared partition again, then uses the existing MR-006 stages. Repeating it against the same local checkpoint reuses verified results. A fresh `prepare` requires a fresh private state directory. Keep the same seed and protocol when verifying reproduction.
