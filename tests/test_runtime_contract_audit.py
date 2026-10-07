"""Completeness guarantees for the static runtime-contract audit."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.verify_runtime_contracts import audit_runtime


class RuntimeContractAuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.package = Path(self.temporary.name) / "play_anything"
        self.package.mkdir()
        (self.package / "module.py").write_text("value = 1\n", encoding="utf-8")

    def test_walk_errors_are_reported_as_incomplete_audits(self):
        def failed_walk(root, *, followlinks, onerror):
            self.assertFalse(followlinks)
            onerror(PermissionError("permission denied", None, str(self.package / "blocked")))
            yield str(self.package), [], ["module.py"]

        with patch("scripts.verify_runtime_contracts.os.walk", side_effect=failed_walk):
            report = audit_runtime(self.package)

        self.assertFalse(report["passed"])
        self.assertEqual(report["checked_files"], 1)
        self.assertTrue(any(item["kind"] == "traversal_error" for item in report["violations"]))

    def test_symlinked_runtime_directories_are_reported_without_traversal(self):
        def walk_symlink(root, *, followlinks, onerror):
            self.assertFalse(followlinks)
            self.assertIsNotNone(onerror)
            child_names = [".git", "node_modules", "linked"]
            yield str(self.package), child_names, ["module.py"]
            self.assertEqual(child_names, [])

        def is_symlink(path):
            return path.name == "linked"

        with patch("scripts.verify_runtime_contracts.os.walk", side_effect=walk_symlink), patch.object(
                Path, "is_symlink", autospec=True, side_effect=is_symlink):
            report = audit_runtime(self.package)

        self.assertFalse(report["passed"])
        kinds = [item["kind"] for item in report["violations"]]
        self.assertEqual(kinds, ["skipped_symlink_directory"])
        self.assertEqual(report["checked_files"], 1)


if __name__ == "__main__":
    unittest.main()
