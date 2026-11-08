import json
from pathlib import Path
from shutil import copytree
from tempfile import TemporaryDirectory
import unittest

from morpheus_tools import handoff
from morpheus_tools.tools import research_registry as registry


class RegistryTests(unittest.TestCase):
    def test_accepted_iris_and_pending_wine_remain_distinct(self):
        entries = {x["hypothesis_id"]: x for x in registry.inventory()}
        self.assertEqual(entries["iris-sepal-gain"]["result"], "NOT_SUPPORTED_ON_FIXED_SPLIT")
        self.assertEqual(entries["iris-sepal-gain"]["review"], "LYRA_INTERNAL_REVIEW")
        self.assertEqual(entries["wine-alcohol-color"]["review"], "AWAITING_LYRA")
        self.assertIsNotNone(entries["wine-alcohol-color"]["result"])

    def test_old_evidence_and_duplicate_version_cannot_be_replaced(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            copytree(registry.ROOT / "lab", root / "lab", ignore=lambda _, names: {".state", "__pycache__"} & set(names))
            ledger = root / "lab/registry.jsonl"
            original = ledger.read_text(encoding="utf-8")
            ledger.write_text(original + original.splitlines()[0] + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "invalid_protocol_history"):
                registry.inventory(root)
            ledger.write_text(original, encoding="utf-8")
            result = root / "lab/evidence/iris-sepal-v1.json"
            payload = json.loads(result.read_bytes())
            payload["result"] = "SUPPORTED"
            result.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "result_integrity_failed"):
                registry.inventory(root)


class HandoffTests(unittest.TestCase):
    def test_interruptions_stop_replay_and_confirmed_receipts_are_reused(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = {"pr": handoff.GITHUB + "/pull/99", "ci": handoff.GITHUB + "/actions/runs/101",
                    "head": "a" * 40, "thread": "1794065078.911019"}
            self.assertEqual(handoff.transfer(plan, "drive", "reserve", root=root)["status"], "SEND_ONCE")
            self.assertEqual(handoff.transfer(plan, "drive", "reserve", root=root)["status"], "RECONCILE")
            with self.assertRaises(OSError):
                handoff.transfer(plan, "slack", "reserve", root=root)
            drive = "https://drive.google.com/file/d/Test_1/view"
            handoff.transfer(plan, "drive", "record", drive, root=root)
            self.assertEqual(handoff.transfer(plan, "slack", "reserve", root=root)["status"], "SEND_ONCE")
            self.assertEqual(handoff.transfer(plan, "slack", "reserve", root=root)["status"], "RECONCILE")
            slack = ("https://" + handoff.WORKSPACE + "/archives/" + handoff.CHANNEL
                     + "/p123?thread_ts=" + plan["thread"] + "&cid=" + handoff.CHANNEL)
            with self.assertRaises(ValueError):
                handoff.transfer(plan, "slack", "record", slack.replace(plan["thread"], "123.000001"), root=root)
            handoff.transfer(plan, "slack", "record", slack, root=root)
            retry = plan | {"ci": handoff.GITHUB + "/actions/runs/102"}
            self.assertEqual(handoff.transfer(retry, "slack", "reserve", root=root)["status"], "ALREADY_RECORDED")
