import inspect
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from play_anything.adapters.repo_rpg_generator import RepoRPGGenerator
from play_anything.engine import PlayAnythingEngine


class WorldSourceBudgetTests(unittest.TestCase):
    def make_repo(self, files):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name) / "repo"
        root.mkdir()
        for name, source in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(source if isinstance(source, bytes) else source.encode("utf-8"))
        return root

    def test_default_world_api_and_analysis_metadata_are_unchanged(self):
        root = self.make_repo({"a.py": "x = 1\n"})
        world = PlayAnythingEngine().generate_world(str(root))
        direct = RepoRPGGenerator.scan_local_directory(str(root))
        self.assertEqual(list(inspect.signature(PlayAnythingEngine.generate_world).parameters),
                         ["self", "repo_path"])
        self.assertIsNone(world.analysis)
        self.assertIsNone(direct.analysis)
        self.assertEqual([node.name for node in world.nodes], ["a.py"])

    def test_engine_budget_exposes_read_totals_and_partial_exclusions(self):
        first = b"x = 1\n"
        second = b"def expensive_source(): return 2\n"
        root = self.make_repo({"a.py": first, "b.py": second})
        world = PlayAnythingEngine(max_total_source_bytes=len(first)).generate_world(str(root))
        analysis = world.analysis
        self.assertEqual(len(world.nodes), 2)
        self.assertEqual(analysis["source_kind"], "repository")
        self.assertEqual(analysis["status"], "partial")
        self.assertEqual(analysis["file_count"], 2)
        self.assertEqual(analysis["analysis_counts"], {
            "python_ast": 1, "source_budget_exceeded": 1,
        })
        self.assertEqual(analysis["source_bytes_read"], len(first))
        self.assertEqual(analysis["source_budget_bytes"], len(first))
        self.assertEqual(analysis["source_budget_exceeded_files"], 1)
        self.assertTrue(analysis["source_budget_exhausted"])
        self.assertTrue(analysis["source_metrics_available"])
        self.assertTrue(analysis["world_materialized_in_memory"])

    def test_zero_budget_inventories_without_opening_nonempty_sources(self):
        root = self.make_repo({"a.py": b"x" * 100000, "b.py": "y = 2\n"})
        with patch("play_anything.adapters.repository_index._read_bounded_source",
                   side_effect=AssertionError("source reader called")) as reader:
            world = RepoRPGGenerator.scan_local_directory(
                str(root), max_files=None, max_total_source_bytes=0)
        reader.assert_not_called()
        self.assertEqual(len(world.nodes), 2)
        self.assertEqual(world.analysis["source_bytes_read"], 0)
        self.assertEqual(world.analysis["source_budget_exceeded_files"], 2)
        self.assertEqual(world.analysis["status"], "partial")

    def test_exact_budget_fill_is_complete_and_marks_boundary(self):
        source = b"x = 1\n"
        root = self.make_repo({"a.py": source})
        world = RepoRPGGenerator.scan_local_directory(
            str(root), max_files=None, max_total_source_bytes=len(source))
        self.assertEqual(world.analysis["status"], "complete")
        self.assertEqual(world.analysis["source_bytes_read"], len(source))
        self.assertTrue(world.analysis["source_budget_exhausted"])
        self.assertEqual(world.analysis["source_budget_exceeded_files"], 0)

    def test_budgeted_file_limit_lookahead_is_counted_but_not_materialized(self):
        first = b"x = 1\n"
        second = b"y = 2\n"
        root = self.make_repo({"a.py": first, "b.py": second})
        world = RepoRPGGenerator.scan_local_directory(
            str(root), max_files=1, max_total_source_bytes=100)
        analysis = world.analysis
        self.assertEqual(len(world.nodes), 1)
        self.assertEqual(analysis["file_count"], 1)
        self.assertEqual(analysis["analysis_counts"], {"python_ast": 1})
        self.assertTrue(analysis["file_limit_reached"])
        self.assertEqual(analysis["file_limit"], 1)
        self.assertEqual(analysis["source_bytes_read"], len(first) + len(second))
        self.assertEqual(analysis["status"], "partial")

    def test_budgeted_lookahead_closes_summary_iterator_on_early_exit(self):
        root = self.make_repo({"a.py": "x = 1\n"})
        closed = []

        def summaries(*args, **kwargs):
            try:
                for name in ("a.py", "b.py"):
                    yield {
                        "path": name, "lines_of_code": 1, "complexity": 1.0,
                        "imports": [], "analysis": "python_ast",
                        "source_bytes_read": 1, "source_budget_bytes": 10,
                        "source_budget_exceeded_files": 0,
                        "source_budget_exhausted": False,
                    }
            finally:
                closed.append(True)

        with patch("play_anything.adapters.repo_rpg_generator.iter_repository_summaries",
                   side_effect=summaries):
            world = RepoRPGGenerator.scan_local_directory(
                str(root), max_files=1, max_total_source_bytes=10)
        self.assertTrue(world.analysis["file_limit_reached"])
        self.assertEqual(closed, [True])

    def test_root_permission_errors_propagate_and_files_are_not_directories(self):
        root = self.make_repo({"a.py": "x = 1\n"})
        with patch("play_anything.adapters.repo_rpg_generator.os.stat",
                   side_effect=PermissionError("root access denied")):
            with self.assertRaisesRegex(PermissionError, "root access denied"):
                RepoRPGGenerator.scan_local_directory(str(root))
        with self.assertRaises(NotADirectoryError):
            RepoRPGGenerator.scan_local_directory(str(root / "a.py"))

    def test_empty_repository_fallback_is_explicit_in_budget_metadata(self):
        root = self.make_repo({})
        world = PlayAnythingEngine(max_total_source_bytes=0).generate_world(str(root))
        self.assertGreater(len(world.nodes), 0)
        self.assertEqual(world.analysis["source_kind"], "synthetic_fallback")
        self.assertEqual(world.analysis["status"], "empty")
        self.assertEqual(world.analysis["file_count"], 0)
        self.assertEqual(world.analysis["source_bytes_read"], 0)
        self.assertEqual(world.analysis["source_budget_exceeded_files"], 0)

    def test_unsupported_language_is_included_but_marks_source_analysis_partial(self):
        root = self.make_repo({"notes.md": "plain text\n"})
        world = RepoRPGGenerator.scan_local_directory(
            str(root), max_total_source_bytes=100)
        self.assertEqual(len(world.nodes), 1)
        self.assertEqual(world.analysis["analysis_counts"], {"unparsed_language": 1})
        self.assertEqual(world.analysis["status"], "partial")

    def test_invalid_budget_fails_before_path_access(self):
        for value in (True, False, -1, 1.5, sys.maxsize):
            with self.subTest(value=value), patch(
                    "play_anything.adapters.repo_rpg_generator.os.path.isdir",
                    side_effect=AssertionError("filesystem checked")):
                with self.assertRaises(ValueError):
                    RepoRPGGenerator.scan_local_directory("missing", max_total_source_bytes=value)
        with self.assertRaises(ValueError):
            PlayAnythingEngine(max_total_source_bytes=True)


if __name__ == "__main__":
    unittest.main()
