import os
import subprocess
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from morpheus_tools.cli import _fingerprint
from morpheus_tools.tools.compare import execute


class ArtifactCompareTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def compare(self, left, right):
        return execute(Namespace(left=str(left), right=str(right), max_files=20), "compare")

    def test_directory_with_sentinel_name_does_not_match_standalone_file(self):
        standalone = self.root / "artifact.txt"
        standalone.write_text("synthetic", encoding="utf-8")
        directory = self.root / "collection"
        directory.mkdir()
        (directory / "__single_file__").write_text("synthetic", encoding="utf-8")

        self.assertFalse(self.compare(standalone, directory)["match"])

    def test_inaccessible_subtree_does_not_look_like_an_empty_tree(self):
        def denied(_path, *, onerror=None, **_kwargs):
            if onerror is not None:
                onerror(PermissionError("synthetic directory denied"))
            return iter(())

        with patch("os.walk", side_effect=denied), self.assertRaises(PermissionError):
            self.compare(self.root, self.root)
        with patch("os.walk", side_effect=denied), self.assertRaises(PermissionError):
            _fingerprint(self.root, "metadata")

    def test_root_nested_and_ancestor_aliases_are_rejected(self):
        target = self.root / "target"
        target.mkdir()
        (target / "synthetic.txt").write_text("synthetic", encoding="utf-8")
        container = self.root / "container"
        container.mkdir()
        alias = container / "alias"
        if os.name == "nt":
            result = subprocess.run(["cmd", "/d", "/c", "mklink", "/J", str(alias), str(target)],
                                    capture_output=True, timeout=15)
            if result.returncode != 0:
                self.skipTest("Windows junction creation unavailable")
        else:
            alias.symlink_to(target, target_is_directory=True)

        for left in (alias, container, alias / "synthetic.txt"):
            with self.subTest(input_type=left.name):
                with self.assertRaisesRegex(ValueError, "symlink_or_reparse_point_not_allowed"):
                    self.compare(left, target)
                with self.assertRaisesRegex(ValueError, "symlink_or_reparse_point_not_allowed"):
                    _fingerprint(left, "content")
