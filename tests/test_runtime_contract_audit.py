"""Completeness guarantees for the static runtime-contract audit."""

from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

from scripts.verify_runtime_contracts import audit_runtime, _read_regular_source


class RuntimeContractAuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.package = Path(self.temporary.name) / "play_anything"
        self.package.mkdir()
        (self.package / "module.py").write_text("value = 1\n", encoding="utf-8")

    def test_symlinked_runtime_file_is_rejected_without_reading_target(self):
        with tempfile.TemporaryDirectory() as outside:
            external = Path(outside) / 'external.py'
            external.write_text('import math\n')
            linked = self.package / 'linked.py'
            try:
                linked.symlink_to(external)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(str(exc))
            with patch('scripts.verify_runtime_contracts._read_regular_source',
                       wraps=_read_regular_source) as reader:
                report = audit_runtime(self.package)
            self.assertFalse(report['passed'])
            self.assertEqual([str(call.args[0]) for call in reader.call_args_list],
                             [str(self.package / 'module.py')])
            self.assertTrue(any(item['file'] == 'linked.py' and item['kind'] == 'nonregular_source'
                                for item in report['violations']))

    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'Requires POSIX FIFO support')
    def test_fifo_runtime_file_is_rejected_without_open(self):
        fifo = self.package / 'blocked.py'
        os.mkfifo(fifo)
        original = os.open

        def guard(path, flags, *args, **kwargs):
            if Path(path) == fifo:
                self.fail('The static audit must not open a known FIFO')
            return original(path, flags, *args, **kwargs)

        with patch('scripts.verify_runtime_contracts.os.open', side_effect=guard):
            report = audit_runtime(self.package)
        self.assertFalse(report['passed'])
        self.assertTrue(any(item['file'] == 'blocked.py' and item['kind'] == 'nonregular_source'
                            for item in report['violations']))

    def test_python_source_encodings_follow_ast_parser_rules(self):
        for raw in [b"# coding: latin-1\nname='caf\xe9'\n",
                    b"\xef\xbb\xbfvalue=1\n"]:
            with self.subTest(raw=raw):
                (self.package / 'encoded.py').write_bytes(raw)
                report = audit_runtime(self.package)
                self.assertTrue(report['passed'], report['violations'])
                self.assertEqual(report['checked_files'], 2)

    def test_excessively_deep_ast_is_a_structured_failed_audit(self):
        # Python 3.11 raises this for deep binop ASTs; later parsers can accept
        # the same source. Inject that real parser failure for a stable contract.
        with patch('scripts.verify_runtime_contracts.ast.parse',
                   side_effect=RecursionError('AST exceeds supported parser depth')):
            report = audit_runtime(self.package)
        self.assertFalse(report['passed'])
        self.assertTrue(any(item['file'] == 'module.py' and item['kind'] == 'syntax_or_read'
                            for item in report['violations']))

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
