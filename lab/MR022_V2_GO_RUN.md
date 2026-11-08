# MR-022 V2 GO_RUN

The [one-cycle authorization](https://morpheusresea-9xx8372.slack.com/archives/C0CGMC7NRL0/p1794167395390289) applies to the reviewed V2 preflight. The manual runner binds the reviewed main revision, exact preflight, unchanged V1 feature/model implementation and current executor freeze. It checks the original bytes, publisher metadata, installed versions and recomputed V2 membership before the fit stage. The model sees only the nine descriptors, training labels and holdout descriptors.

Set `$original` and `$metadata` to the verified local original CSV and official V1 release metadata. Create the ignored `.morpheus/aqsol-v2-run` working folder. Use the already installed V1 Docker dependency volume. Execute the synthetic tests after committing the executor.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File lab/aqsol_v2_go.ps1 -Phase Test
powershell -NoProfile -ExecutionPolicy Bypass -File lab/aqsol_v2_go.ps1 -Phase Run -OriginalCsv $original -DataverseMetadata $metadata
```

The wrapper writes a durable launch intent once. It keeps one MR-006 checkpoint under the workspace's `.morpheus/mr022-v2-go-run/checkpoint`. The isolated worker has no network or credentials and mounts the source, code and dependencies read-only. Only the dedicated checkpoint is writable.

An uncertain launch or missing checkpoint requires reconciliation. With the prior container gone and its intact checkpoint located, the same command with `-Phase Resume` can reuse it. A completed fit is never repeated. MR-006 treats an interrupted fit as nonretryable. A completed checkpoint returns its verified aggregate without recalculation. Keep row-level predictions and SQLite local.
