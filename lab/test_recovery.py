"""Exercise checkpoint recovery with synthetic actions and real process stops."""

from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import Mock

import lab


HERE = Path(__file__).resolve().parent
PACKET = {"task": "synthetic-control", "values": [1, -1]}
RESUME = "py lab/lab.py resume --task synthetic-control"


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.state = self.root / "state"

    def run_stages(self, *stages, **options):
        return lab.run(self.state, packet=PACKET, stages=stages, **options)

    def child(self, code, *args):
        process = subprocess.Popen(
            [sys.executable, "-c", code, str(self.state), *args],
            cwd=HERE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        self.addCleanup(self.stop, process)
        return process

    @staticmethod
    def stop(process):
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=15)

    def wait_for_marker(self, marker, process):
        deadline = time.monotonic() + 30
        while not (self.root / marker).exists():
            if process.poll() is not None:
                self.fail(f"Child exited before {marker}: {process.communicate()[1]}")
            if time.monotonic() >= deadline:
                self.fail(f"Timed out waiting for {marker}")
            time.sleep(0.02)

    def test_completed_stages_are_reused(self):
        prepare = Mock(return_value={"value": 3})
        compute = Mock(return_value={"value": 9})
        stages = (lab.Stage("prepare", prepare), lab.Stage("compute", compute))
        first = self.run_stages(*stages)
        second = self.run_stages(*stages)
        self.assertEqual(first["status"], "COMPLETED")
        self.assertFalse(first["reused"])
        self.assertEqual(second["status"], "COMPLETED")
        self.assertTrue(second["reused"])
        self.assertEqual(second["artifact"], {"value": 9})
        prepare.assert_called_once_with(None)
        compute.assert_called_once_with({"value": 3})

    def test_429_wait_is_durable_and_requires_a_due_explicit_retry(self):
        action = Mock(side_effect=[lab.QuotaRejected(10), {"value": 1}])
        stage = lab.Stage("request", action, external=True)
        first = self.run_stages(stage, clock=lambda: 100)
        self.assertEqual(first["status"], "WAITING_QUOTA")
        self.assertEqual(first["next_command"], RESUME + " --retry-quota")
        self.assertEqual(self.run_stages(stage, retry_quota=True, clock=lambda: 109)["status"], "WAITING_QUOTA")
        self.assertEqual(self.run_stages(stage, clock=lambda: 110)["status"], "WAITING_QUOTA")
        action.assert_called_once_with(None)
        self.assertEqual(self.run_stages(stage, retry_quota=True, clock=lambda: 110)["status"], "COMPLETED")
        self.assertEqual(action.call_count, 2)

    def test_second_429_stays_waiting_without_another_request(self):
        action = Mock(side_effect=lab.QuotaRejected(1))
        stage = lab.Stage("request", action, external=True)
        self.run_stages(stage, clock=lambda: 100)
        self.run_stages(stage, retry_quota=True, clock=lambda: 101)
        result = self.run_stages(stage, retry_quota=True, clock=lambda: 200)
        self.assertEqual(result["status"], "WAITING_QUOTA")
        self.assertIsNone(result["next_command"])
        self.assertEqual(action.call_count, 2)

    def test_external_transport_failure_never_replays_unknown_request(self):
        action = Mock(side_effect=ConnectionError("synthetic transport details"))
        stage = lab.Stage("request", action, external=True)
        first = self.run_stages(stage)
        second = self.run_stages(stage, retry_quota=True)
        for result in (first, second):
            self.assertEqual(result["status"], "FAILED")
            self.assertEqual(result["reason"], "external_result_unknown")
            self.assertIsNone(result["next_command"])
            self.assertNotIn("synthetic transport details", json.dumps(result))
        action.assert_called_once_with(None)

    def kill_during_second_stage(self, external):
        child = self.child("""
import json
from pathlib import Path
import sys
import time
import lab

state = Path(sys.argv[1])
external = sys.argv[3] == "external"
def pause():
    (state.parent / "stage-entered").touch()
    time.sleep(90)

def interrupted(previous):
    assert previous == {"value": 3}
    if external:
        pause()
    return {"value": 8}

save = lab.save
def instrument(db, stage, status, **kwargs):
    if stage == "compute" and status == "COMPLETED":
        db.set_trace_callback(lambda statement: pause() if statement == "COMMIT" else None)
    return save(db, stage, status, **kwargs)
lab.save = instrument

stages = (lab.Stage("prepare", lambda _: {"value": 3}),
          lab.Stage("compute", interrupted, external=external))
lab.run(state, packet=json.loads(sys.argv[2]), stages=stages)
""", json.dumps(PACKET), "external" if external else "local")
        self.wait_for_marker("stage-entered", child)
        self.stop(child)
        self.assertNotEqual(child.returncode, 0)
        with closing(sqlite3.connect(self.state / "evidence.sqlite3")) as db:
            self.assertEqual(
                dict(db.execute("SELECT stage, status FROM checkpoints")),
                {"prepare": "COMPLETED", "compute": "RUNNING"},
            )

    def test_process_kill_resumes_local_stage_without_repeating_completed_stage(self):
        self.kill_during_second_stage(external=False)
        prepare = Mock()
        compute = Mock(return_value={"value": 9})
        result = self.run_stages(lab.Stage("prepare", prepare), lab.Stage("compute", compute))
        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(result["artifact"], {"value": 9})
        prepare.assert_not_called()
        compute.assert_called_once_with({"value": 3})

    def test_process_kill_does_not_repeat_external_request(self):
        self.kill_during_second_stage(external=True)
        prepare, compute = Mock(), Mock()
        stages = (lab.Stage("prepare", prepare), lab.Stage("compute", compute, external=True))
        for _ in range(2):
            result = self.run_stages(*stages)
            self.assertEqual(result["status"], "FAILED")
            self.assertEqual(result["reason"], "external_result_unknown")
            self.assertIsNone(result["next_command"])
        prepare.assert_not_called()
        compute.assert_not_called()
        self.assertEqual(
            {row["stage"]: row["status"] for row in lab.status(self.state)},
            {"prepare": "COMPLETED", "compute": "FAILED"},
        )

    def test_two_processes_do_not_duplicate_stage(self):
        code = """
import json
from pathlib import Path
import sqlite3
import sys
import time
import lab

state = Path(sys.argv[1])
role = sys.argv[3]
connect = sqlite3.connect
def instrument(path, *args, **kwargs):
    db = connect(path, *args, **kwargs)
    if role == "second" and Path(path).name == "worker.sqlite3":
        db.set_trace_callback(lambda sql: (state.parent / "second-lock-attempt").touch()
                              if sql == "BEGIN IMMEDIATE" else None)
    return db
sqlite3.connect = instrument

def work(previous):
    with (state.parent / "calls").open("a", encoding="utf-8") as stream:
        stream.write(role + "\\n")
    (state.parent / "stage-entered").touch()
    deadline = time.monotonic() + 30
    while not (state.parent / "release").exists():
        if time.monotonic() >= deadline:
            raise TimeoutError("test worker not released")
        time.sleep(0.02)
    return {"value": 9}

print(json.dumps(lab.run(state, packet=json.loads(sys.argv[2]),
                         stages=(lab.Stage("compute", work),))))
"""
        first = self.child(code, json.dumps(PACKET), "first")
        self.wait_for_marker("stage-entered", first)
        second = self.child(code, json.dumps(PACKET), "second")
        self.wait_for_marker("second-lock-attempt", second)
        (self.root / "release").touch()
        for worker in (first, second):
            output, error = worker.communicate(timeout=30)
            self.assertEqual(worker.returncode, 0, error)
            self.assertIn(json.loads(output)["status"], {"COMPLETED", "RUNNING"})
        self.assertEqual((self.root / "calls").read_text(encoding="utf-8").splitlines(), ["first"])
        compute = Mock()
        final = self.run_stages(lab.Stage("compute", compute))
        self.assertTrue(final["reused"])
        self.assertEqual(final["artifact"], {"value": 9})
        compute.assert_not_called()

    def test_changed_input_refuses_resume(self):
        compute = Mock(return_value={"value": 9})
        stages = (lab.Stage("compute", compute),)
        self.run_stages(*stages)
        with self.assertRaises(lab.CheckpointError):
            lab.run(self.state, packet=PACKET | {"values": [2, -1]}, stages=stages)
        compute.assert_called_once_with(None)

    def test_corrupted_earlier_result_refuses_reuse(self):
        prepare = Mock(return_value={"value": 3})
        compute = Mock(return_value={"value": 9})
        stages = (lab.Stage("prepare", prepare), lab.Stage("compute", compute))
        self.run_stages(*stages)
        with closing(sqlite3.connect(self.state / "evidence.sqlite3")) as db, db:
            db.execute("UPDATE checkpoints SET result=? WHERE stage='prepare'", ('{"value":6}',))
        with self.assertRaises(lab.CheckpointError):
            self.run_stages(*stages)
        prepare.assert_called_once_with(None)
        compute.assert_called_once_with({"value": 3})

    def test_tampered_external_state_cannot_enable_replay(self):
        action = Mock(side_effect=ConnectionError)
        stage = lab.Stage("request", action, external=True)
        self.assertEqual(self.run_stages(stage)["status"], "FAILED")
        with closing(sqlite3.connect(self.state / "evidence.sqlite3")) as db, db:
            db.execute("UPDATE checkpoints SET status='PENDING' WHERE stage='request'")
        with self.assertRaisesRegex(lab.CheckpointError, "corrupt_checkpoint"):
            self.run_stages(stage, retry_quota=True)
        action.assert_called_once_with(None)

    def test_legacy_checkpoint_is_not_reinitialized(self):
        self.state.mkdir()
        database = self.state / "evidence.sqlite3"
        with closing(sqlite3.connect(database)) as db, db:
            db.execute("CREATE TABLE events (phase TEXT)")
            db.execute("INSERT INTO events VALUES ('VERIFIED')")
        original = database.read_bytes()
        action = Mock()
        with self.assertRaises(lab.CheckpointError):
            self.run_stages(lab.Stage("compute", action))
        self.assertEqual(database.read_bytes(), original)
        action.assert_not_called()


if __name__ == "__main__":
    unittest.main()
