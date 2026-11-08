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

## MR-004 · reproducible public pilot

Inspect the [frozen hypothesis and protocol](protocols/iris-sepal-v1.json), then use the same offline runner:

```powershell
py lab/lab.py protocol --task iris-sepal-v1
py lab/lab.py run --task iris-sepal-v1
py lab/lab.py status --task iris-sepal-v1
py lab/lab.py resume --task iris-sepal-v1
```

The Iris pilot uses only Python's standard library and the pinned public file. Attribution: Fisher, R. (1936), [Iris, UCI Machine Learning Repository](https://doi.org/10.24432/C56C76), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The repository fixture is the unmodified UCI `bezdekIris.data` byte stream. The input hash and frozen method precede the calculation in commit `1e70244`.

Each stage uses the existing MR-006 checkpoint. The runner first freezes the split, then computes predictions, then checks held-out membership and evaluates the candidate, baseline and shuffled-label negative control. The [aggregate evidence](evidence/iris-sepal-v1.json) is reproduced in a fresh state by the tests. Finished results remain in the original experiment checkpoint. For a changed research protocol, give it a new version and keep prior files and checkpoints.

The result applies to the fixed public split. `COMPLETED` records engineering execution, and `AWAITING_LYRA` records the outstanding scientific review. The pilot grants no clinical admission.
