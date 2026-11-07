"""Regression tests: bounded output, completeness, privacy and cache provenance."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from morpheus_tools.cli import main


class ToolLibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.old_cwd = Path.cwd()
        os.chdir(self.base)
        self.addCleanup(lambda: os.chdir(self.old_cwd))

    def call(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(list(args))
        return code, json.loads(output.getvalue())

    def put(self, name, text):
        path = self.base / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return str(path)

    def test_catalog_and_validation(self):
        code, result = self.call("validate")
        self.assertEqual(code, 0)
        self.assertEqual(result["total"], 14)
        self.assertEqual(result["executable"], 4)
        code, matches = self.call("find", "пустое", "множество")
        self.assertEqual(code, 0)
        self.assertTrue(any(x["id"] == "dataset.empty-check" for x in matches))
        code, info = self.call("describe", "log.triage")
        self.assertEqual(code, 0)
        self.assertEqual(info["id"], "log.triage")

    def test_empty_table_fails(self):
        file = self.put("empty.csv", "split,score\n")
        code, out = self.call("run", "dataset.empty-check", "--input", file, "--expect-subset", "split=train")
        self.assertEqual(code, 2)
        self.assertEqual(out["status"], "failed_check")
        self.assertEqual(out["empty_subsets"], ["check_1"])
        self.assertEqual(out["rows_scanned"], 0)

    def test_empty_subset_and_zero_based_names(self):
        file = self.put("split.csv", "split,score\ntrain,1\ntrain,2\n")
        code, out = self.call("run", "dataset.empty-check", "--input", file, "--expect-subset", "split=train", "--expect-subset", "split=test")
        self.assertEqual(code, 2)
        self.assertEqual(out["empty_subsets"], ["check_2"])
        report = json.loads(Path(out["report_path"]).read_text("utf-8"))
        self.assertEqual(report["checks"][0]["matching_rows"], 2)

    def test_incomplete_scan_does_not_claim_empty(self):
        file = self.put("split.csv", "split\ntrain\ntrain\ntest\n")
        code, out = self.call("run", "dataset.empty-check", "--input", file, "--expect-subset", "split=test", "--max-rows", "2")
        self.assertEqual(code, 3)
        self.assertEqual(out["status"], "partial")
        self.assertEqual(out["empty_subsets"], [])
        self.assertFalse(out["scan_complete"])

    def test_missing_column(self):
        file = self.put("split.csv", "split\ntrain\n")
        code, out = self.call("run", "dataset.empty-check", "--input", file, "--require-column", "subject_id")
        self.assertEqual(code, 2)
        self.assertEqual(out["missing_columns"], ["subject_id"])

    def test_incomplete_jsonl_does_not_claim_unseen_column_is_missing(self):
        file = self.put("split.jsonl", '{"split":"train"}\n{"cohort":"test"}\n')
        args = ("run", "dataset.empty-check", "--input", file, "--require-column", "cohort",
                "--expect-subset", "cohort=test")
        code, out = self.call(*args, "--max-rows", "1")
        self.assertEqual((code, out["status"]), (3, "partial"))
        self.assertFalse(out["scan_complete"])
        self.assertEqual(out["missing_columns"], [])
        self.assertEqual(out["empty_subsets"], [])
        check = json.loads(Path(out["report_path"]).read_text("utf-8"))["checks"][0]
        self.assertIsNone(check["column_present"])
        self.assertIsNone(check["empty"])

        code, out = self.call(*args)
        self.assertEqual((code, out["status"]), (0, "ok"))
        check = json.loads(Path(out["report_path"]).read_text("utf-8"))["checks"][0]
        self.assertTrue(check["column_present"])
        self.assertEqual(check["matching_rows"], 1)

    def test_profile_no_raw_values(self):
        secret = "SENSITIVE_PARTICIPANT_999"
        file = self.put("data.csv", "split,participant,score\ntrain," + secret + ",2\ntest,,\n")
        code, out = self.call("run", "dataset.profile", "--input", file)
        self.assertEqual(code, 0)
        raw = json.dumps(out) + Path(out["report_path"]).read_text("utf-8")
        self.assertNotIn(secret, raw)
        report = json.loads(Path(out["report_path"]).read_text("utf-8"))
        self.assertEqual(report["column_presence"]["participant"]["empty"], 1)

    def test_invalid_arguments_redact_values_and_exit_one(self):
        canary = "FAUX_ARGUMENT_TOKEN_7823"
        for args in ((canary,), ("run", "dataset.profile", "--input", "sample.csv", "--max-rows", canary)):
            with self.subTest(args=args):
                stdout, stderr = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    code = main(list(args))
                self.assertEqual(code, 1)
                self.assertEqual(json.loads(stdout.getvalue())["code"], "invalid_arguments")
                self.assertNotIn(canary, stdout.getvalue() + stderr.getvalue())

    def test_discovery_json_survives_legacy_windows_encoding(self):
        buffer = io.BytesIO()
        with io.TextIOWrapper(buffer, encoding="cp1252") as output:
            with contextlib.redirect_stdout(output):
                code = main(["describe", "dataset.empty-check"])
            output.flush()
            result = json.loads(buffer.getvalue())
        self.assertEqual(code, 0)
        self.assertIn("пустое множество", result["triggers"])

    def test_jsonl_and_invalid_record(self):
        file = self.put("data.jsonl", '{"a":1,"b":null}\n{"a":2}\n')
        code, out = self.call("run", "dataset.profile", "--input", file)
        self.assertEqual(code, 0)
        report = json.loads(Path(out["report_path"]).read_text("utf-8"))
        self.assertEqual(report["column_presence"]["b"]["empty"], 2)
        file = self.put("bad.jsonl", '{"a":1}\nnot-json\n')
        code, out = self.call("run", "dataset.profile", "--input", file)
        self.assertEqual(code, 1)
        self.assertEqual(out["status"], "error")
        self.assertNotIn("not-json", json.dumps(out))

    def test_log_triage_never_echoes_lines(self):
        token = "xoxb-DO_NOT_ECHO_THIS"
        file = self.put("run.log", "rate limit 429 for " + token + "\nERROR: timeout\nTraceback (most recent call last)\n")
        code, out = self.call("run", "log.triage", "--input", file)
        self.assertEqual(code, 0)
        report_text = Path(out["report_path"]).read_text("utf-8")
        self.assertNotIn(token, report_text)
        self.assertEqual(json.loads(report_text)["indicators"]["quota"]["count"], 1)

    def test_compare_files_match_and_mismatch_without_hashes(self):
        a = self.put("a.txt", "same")
        b = self.put("b.txt", "same")
        code, out = self.call("run", "artifact.compare", "--left", a, "--right", b)
        self.assertEqual(code, 0)
        self.assertTrue(out["match"])
        Path(b).write_text("different", encoding="utf-8")
        code, out = self.call("run", "artifact.compare", "--left", a, "--right", b)
        self.assertEqual(code, 2)
        self.assertFalse(out["match"])
        self.assertNotIn("sha256", json.dumps(out).lower())

    def test_compare_directory_mismatch(self):
        self.put("left/a.txt", "same")
        self.put("right/a.txt", "same")
        self.put("left/extra.txt", "extra")
        code, out = self.call("run", "artifact.compare", "--left", "left", "--right", "right")
        self.assertEqual(code, 2)
        self.assertEqual(out["only_left_count"], 1)

    def test_metadata_cache_marks_provenance(self):
        file = self.put("data.csv", "a\n1\n")
        a, first = self.call("run", "dataset.profile", "--input", file, "--cache-mode", "metadata")
        b, second = self.call("run", "dataset.profile", "--input", file, "--cache-mode", "metadata")
        self.assertEqual((a, b), (0, 0))
        self.assertEqual(first["cache"], "miss")
        self.assertEqual(second["cache"], "hit")
        self.assertIn("not_for_scientific_proof", second["provenance"])

    def test_content_cache_invalidates_change(self):
        file = self.put("data.csv", "a\n1\n")
        _, first = self.call("run", "dataset.profile", "--input", file, "--cache-mode", "content")
        _, second = self.call("run", "dataset.profile", "--input", file, "--cache-mode", "content")
        self.assertEqual(first["cache"], "miss")
        self.assertEqual(second["cache"], "hit")
        self.assertEqual(second["provenance"], "content_verified")
        Path(file).write_text("a\n2\n3\n", encoding="utf-8")
        _, third = self.call("run", "dataset.profile", "--input", file, "--cache-mode", "content")
        self.assertEqual(third["cache"], "miss")

    def test_existing_eeg_commands_discoverable_but_not_exec_from_catalog(self):
        code, listing = self.call("list")
        self.assertEqual(code, 0)
        self.assertEqual(len(listing), 14)
        self.assertTrue(any(x["id"] == "eeg.holdout" and x["kind"] == "documented_external" for x in listing))
        code, info = self.call("describe", "eeg.baseline")
        self.assertEqual(code, 0)
        self.assertIn("ocon9000", info["example"])
        code, out = self.call("run", "eeg.holdout")
        self.assertEqual(code, 1)
        self.assertIn("external", out["code"])

    def test_invalid_tool_is_not_executed(self):
        code, out = self.call("run", "evil.tool", "--input", "x")
        self.assertEqual(code, 1)
        self.assertEqual(out["code"], "unknown_tool")

    def test_parquet_error_without_optional_dependency_is_bounded(self):
        file = self.put("some.parquet", "not-parquet")
        code, out = self.call("run", "dataset.profile", "--input", file)
        self.assertEqual(code, 1)
        self.assertEqual(out["status"], "error")


if __name__ == "__main__":
    unittest.main()
