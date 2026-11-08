# MR-019 Dispatcher Iris acceptance

One exact operation is available for the public, nonclinical Iris acceptance. The existing Dispatcher remains idle until the owner explicitly requests the operation in the MR-019 Slack thread. The pilot also requires a local approval with an immutable local Docker image ID and exact source hashes. It never reads or runs MR-003.

## Install on the existing Windows Dispatcher

Review the release commit and verify the existing Linux Docker Engine and a trusted local Python image ID. Keep the private `.env`, queue, logs and deployment out of Git. Back up the existing Dispatcher source and SQLite using SQLite's backup API before editing the live source. Prepare the bounded release from the reviewed repository root. Use an unused approval directory.

```powershell
py -B lab/prepare_dispatcher_pilot.py '<Dispatcher root>/.morpheus/mr019-iris' 'sha256:<local Python image ID>'
```

Add this hook in the existing `app_mention` handler after the existing owner/channel check and `reply` definition. `fetch_list` and the queue path are the existing Dispatcher functions and values. Reload only the existing scheduled task.

```python
pilot_root = BASE / ".morpheus" / "mr019-iris"
if (pilot_root / "dispatcher_pilot.py").is_file():
    from importlib.util import module_from_spec, spec_from_file_location
    spec = spec_from_file_location("dispatcher_pilot", pilot_root / "dispatcher_pilot.py")
    pilot = module_from_spec(spec)
    spec.loader.exec_module(pilot)
    if pilot.handle(event, OWNER_USER_ID, OPS_CHANNEL_ID, QUEUE_DB,
                    pilot_root, pilot_root / "public", lambda: fetch_list(client)[0], reply):
        return
```

From the original MR-019 thread the owner first sends `@Dispatcher queue MR-019` and then `@Dispatcher run MR-019 iris-sepal-v1`. The current Slack List card must match the queued record and be `IN_PROGRESS`. The scientific subprocess has a fixed command, no network or Docker socket, a read-only root and public input mount, a dedicated checkpoint directory, no capabilities, a non-root user, and CPU/memory/PID/file/time limits. The Docker client receives a reduced host environment.

If the outcome is uncertain, check the exact local `morpheus-mr019-iris-sepal-v1` container and its state. Do not create another container while it exists. With the prior invocation reconciled, the owner sends `@Dispatcher resume MR-019 iris-sepal-v1` in the same thread. The existing MR-006 checkpoint verifies the input and stage integrity. Event replays and completed jobs do not rerun the pilot. When the acceptance window ends, rename `approval.json` locally to disable new executions while keeping evidence.

## Verify and deliver

```powershell
py -B lab/dispatch_evidence.py '<Dispatcher root>/.morpheus/dispatch_queue.sqlite3' '<Dispatcher root>/.morpheus/mr019-iris'
```

The export reads the existing queue database and returns only the verified aggregate and digests. Use the existing [review transfer](README.md#review-transfer) with the exact tested PR head and green CI. Reserve each Drive/Slack write using the handoff journal. For an unknown write, look up the original file or thread reply, verify it, then record the receipt before proceeding. Keep Drive closed and never publish the queue or checkpoint. Final publication uses authenticated GitHub, Drive and Slack connectors on the host. The scientific process has no credentials.

The CI Docker check uses the same worker, records an unknown outcome after the actual checkpoint commit, resumes through the journal and confirms the same output with `reused=true`. Windows Slack/Socket Mode acceptance is a separate live check.
