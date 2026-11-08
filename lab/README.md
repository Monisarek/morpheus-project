# MR-006 · recovery of the existing LAB synthetic runner

From this repository's root, using Python 3.10–3.12 with `lab/requirements.txt` installed:

```powershell
py lab/lab.py status
py lab/lab.py run --task synthetic-control
py lab/lab.py resume --task synthetic-control
py -m unittest discover -s lab -v
```

The local SQLite checkpoint records PENDING, RUNNING, COMPLETED, FAILED and WAITING_QUOTA. The completed prefix is verified and reused. Stage outputs, stage state, the input packet and the ordered plan are checked before work starts. A second SQLite file holds the operating system's writer lock across stage execution. Both files belong to the same local state directory.

The resume command above retries an interrupted or failed deterministic local stage. For a provider-confirmed rejection before work, the checkpoint exposes `retry_at` as UTC epoch seconds. After that deadline the caller may explicitly resume once with `py lab/lab.py resume --task synthetic-control --retry-quota`. The CLI task is offline. The external stage contract is exercised using synthetic injected actions. A real adapter must confirm that the provider rejected the operation before performing work and must supply a retry delay. Transport loss, process death after dispatch, and uncertain 429 responses require provider-side reconciliation. In those cases the runner returns no replay command.

Use the same worktree, code and inputs when resuming. Changed inputs, missing or corrupt state and legacy ledgers require operator inspection. The old LAB ledger is left in place, and MR-006 starts with a separate local state directory. Do not remove, swap or roll back checkpoint or lock files. The guarantee applies to cooperating processes sharing this local filesystem and intact state.
