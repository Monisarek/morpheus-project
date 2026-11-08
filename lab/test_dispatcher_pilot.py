import json
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from threading import Event, Thread
import unittest

import dispatcher_pilot as pilot
from dispatch_evidence import export
from prepare_dispatcher_pilot import prepare


class DispatcherPilotTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "pilot"
        self.image = os.environ.get("MORPHEUS_DOCKER_TEST_IMAGE")
        prepare(self.root, self.image or ("sha256:" + "a" * 64))
        self.source = self.root / "public"
        self.db = Path(temp.name) / "dispatch_queue.sqlite3"
        self.calls = []
        self.replies = []
        self.task = {"ID": pilot.TASK, "record_id": pilot.RECORD, "Статус": "IN_PROGRESS"}
        self.result = json.loads((self.source / "evidence/iris-sepal-v1.json").read_bytes())
        with sqlite3.connect(self.db) as db:
            db.execute("CREATE TABLE dispatch_queue (task_id TEXT PRIMARY KEY, slack_record_id TEXT, state TEXT)")
            db.executemany("INSERT INTO dispatch_queue VALUES (?,?,?)",
                           [(pilot.TASK, pilot.RECORD, "PENDING"), ("MR-003", "RecProtected", "PENDING")])

    def event(self, action="run", seq=1, **fields):
        return {"user": "owner", "channel": "ops", "thread_ts": pilot.THREAD,
                "ts": f"1794065079.{seq:06d}", "text": f"<@U0CFBPD8KV5> {action} MR-019 iris-sepal-v1",
                **fields}

    def handle(self, event, executor=None):
        return pilot.handle(event, "owner", "ops", self.db, self.root, self.source,
                            lambda: [self.task], self.replies.append,
                            executor=executor or self.execute)

    def execute(self, root, source, image, resume):
        self.calls.append(resume)
        return {"status": "COMPLETED", "artifact": self.result, "reused": resume}

    def test_exact_authorization_approval_card_and_queue(self):
        for fields in ({"user": "stranger"}, {"channel": "other"}, {"thread_ts": "other"},
                       {"bot_id": "bot"}, {"subtype": "message_changed"},
                       {"text": "<@U0CFBPD8KV5> run MR-003 iris-sepal-v1"},
                       {"text": "<@U0CFBPD8KV5> run MR-019 iris-sepal-v1; calc.exe"},
                       {"text": "> <@U0CFBPD8KV5> run MR-019 iris-sepal-v1"}):
            self.assertFalse(self.handle(self.event(**fields)))
        self.task["Статус"] = "BLOCKED"
        self.assertTrue(self.handle(self.event()))
        self.assertIn("BLOCKED", self.replies[-1])
        self.task["Статус"] = "IN_PROGRESS"
        (self.source / "unexpected.txt").write_text("must not be mounted")
        self.handle(self.event())
        self.assertIn("BLOCKED", self.replies[-1])
        (self.source / "unexpected.txt").unlink()
        (self.root / "approval.json").rename(self.root / "disabled.json")
        self.handle(self.event())
        self.assertIn("BLOCKED", self.replies[-1])
        (self.root / "disabled.json").rename(self.root / "approval.json")
        with sqlite3.connect(self.db) as db:
            db.execute("UPDATE dispatch_queue SET state='CANCELLED' WHERE task_id=?", (pilot.TASK,))
        self.handle(self.event())
        self.assertIn("BLOCKED", self.replies[-1])
        self.assertEqual(self.calls, [])

    def test_unknown_then_explicit_resume_and_replayed_events(self):
        def lost_response(*args):
            self.calls.append(False)
            raise OSError("client interrupted")

        self.handle(self.event(), lost_response)
        self.handle(self.event())
        self.assertEqual(len(self.replies), 1)
        self.handle(self.event("resume", 2))
        self.assertIn("COMPLETED", self.replies[-1])
        self.assertIn("reused=true", self.replies[-1])
        self.handle(self.event("resume", 2))
        self.assertEqual(len(self.replies), 2)
        self.handle(self.event("run", 3))
        self.assertIn("ALREADY_COMPLETED", self.replies[-1])
        self.assertEqual(self.calls, [False, True])
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute("SELECT state FROM dispatch_queue WHERE task_id='MR-003'").fetchone(),
                             ("PENDING",))

    def test_two_executors_and_changed_inputs(self):
        entered, release = Event(), Event()

        def hold(*args):
            entered.set()
            if not release.wait(5):
                raise RuntimeError("test_timeout")
            return self.execute(*args)

        thread = Thread(target=self.handle, args=(self.event(), hold))
        thread.start()
        try:
            self.assertTrue(entered.wait(5))
            self.handle(self.event("resume", 2))
            self.assertIn("BLOCKED", self.replies[-1])
        finally:
            release.set()
            thread.join(5)
        self.assertEqual(self.calls, [False])
        (self.source / "fixtures/iris.csv").write_text("changed", encoding="utf-8")
        self.handle(self.event("resume", 3))
        self.assertIn("BLOCKED", self.replies[-1])
        self.assertEqual(self.calls, [False])


    def test_export_only_verified_completed_aggregate(self):
        self.handle(self.event())
        artifact = export(self.db, self.root)
        self.assertEqual(artifact["artifact"], self.result)
        with sqlite3.connect(self.db) as db:
            db.execute("UPDATE dispatch_iris_receipt SET evidence='bad'")
        with self.assertRaisesRegex(ValueError, "dispatcher_evidence_unconfirmed"):
            export(self.db, self.root)

    def test_real_docker_checkpoint_after_lost_worker_result(self):
        if not self.image:
            self.skipTest("local Docker image ID not supplied")
        state = self.root / "state"
        state.mkdir(mode=0o777)
        state.chmod(0o777)
        if os.name != "nt":
            self.root.parent.chmod(0o755)

        def discard_after_commit(*args):
            first = pilot.docker(*args)
            self.assertEqual(first["artifact"], self.result)
            self.assertFalse(first["reused"])
            return {"status": "RECONCILE"}

        self.handle(self.event(), discard_after_commit)
        self.assertIn("RECONCILE", self.replies[-1])
        self.handle(self.event("resume", 2), pilot.docker)
        self.assertIn("COMPLETED", self.replies[-1])
        self.assertIn("reused=true", self.replies[-1])
        self.handle(self.event("resume", 2), pilot.docker)
        self.assertEqual(len(self.replies), 2)
