import gc
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
import weakref
from unittest.mock import patch

from play_anything.adapters import repository_index
from play_anything.adapters.repository_index import iter_repository_summaries
from play_anything.adapters.repo_rpg_generator import RepoRPGGenerator


class RepositoryIngestionTests(unittest.TestCase):
    def test_optional_source_metrics_preserve_default_shape_and_measure_uncapped_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.py").write_bytes(b"x=1\n")

            ordinary = list(iter_repository_summaries(root, max_files=None))
            measured = list(iter_repository_summaries(
                root, max_files=None, include_source_metrics=True,
            ))
            with self.assertRaises(TypeError):
                list(iter_repository_summaries(
                    root, max_files=None, include_source_metrics=1,
                ))

        self.assertNotIn("source_bytes_read", ordinary[0])
        self.assertEqual(measured[0]["source_bytes_read"], 4)
        self.assertIsNone(measured[0]["source_budget_bytes"])
        self.assertFalse(measured[0]["source_budget_exhausted"])
        self.assertEqual(measured[0]["source_budget_exceeded_files"], 0)

    def test_aggregate_source_budget_is_deterministic_and_inventory_continues(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.py").write_bytes(b"x=1\n")
            (root / "b.py").write_bytes(b"y=2\n")
            (root / "c.py").write_bytes(b"z=3\n")

            summaries = list(iter_repository_summaries(
                root, max_files=None, max_total_source_bytes=5,
            ))

        self.assertEqual([item["path"] for item in summaries], ["a.py", "b.py", "c.py"])
        self.assertEqual([item["analysis"] for item in summaries], [
            "python_ast", "source_budget_exceeded", "source_budget_exceeded",
        ])
        self.assertEqual(summaries[-1]["source_bytes_read"], 4)
        self.assertEqual(summaries[-1]["source_budget_bytes"], 5)
        self.assertEqual(summaries[-1]["source_budget_exceeded_files"], 2)
        self.assertTrue(summaries[-1]["source_budget_exhausted"])

    def test_zero_byte_budget_keeps_empty_files_parseable_and_reads_no_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "empty.py").write_bytes(b"")
            (root / "nonempty.py").write_bytes(b"x = 1\n")

            summaries = list(iter_repository_summaries(
                root, max_files=None, max_total_source_bytes=0,
            ))

        self.assertEqual([item["analysis"] for item in summaries], [
            "python_ast", "source_budget_exceeded",
        ])
        self.assertEqual(summaries[-1]["source_bytes_read"], 0)
        self.assertEqual(summaries[-1]["source_budget_exceeded_files"], 1)
        self.assertTrue(summaries[-1]["source_budget_exhausted"])

    def test_exact_source_budget_fill_is_reached_without_excluding_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.py").write_bytes(b"x = 1\n")

            summaries = list(iter_repository_summaries(
                root, max_files=None, max_total_source_bytes=6,
            ))

        self.assertEqual(summaries[0]["analysis"], "python_ast")
        self.assertEqual(summaries[0]["source_bytes_read"], 6)
        self.assertEqual(summaries[0]["source_budget_exceeded_files"], 0)
        self.assertTrue(summaries[0]["source_budget_exhausted"])

    def test_budget_accounting_is_the_same_with_a_warm_summary_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / "summaries.sqlite"
            (root / "a.py").write_bytes(b"x = 1\n")
            (root / "b.py").write_bytes(b"y = 2\n")

            cold = list(iter_repository_summaries(
                root, max_files=None, cache_path=cache, max_total_source_bytes=20,
            ))
            warm = list(iter_repository_summaries(
                root, max_files=None, cache_path=cache, max_total_source_bytes=20,
            ))

        self.assertEqual([item["analysis"] for item in cold], ["python_ast", "python_ast"])
        self.assertEqual(cold[-1]["source_bytes_read"], warm[-1]["source_bytes_read"])
        self.assertEqual(cold[-1]["source_bytes_read"], 12)

    def test_budget_counts_one_byte_sentinel_when_source_grows_after_stat(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root.resolve() / "a.py"
            source.write_bytes(b"x = 1\n")
            original_stat = Path.stat

            def stale_stat(path, *args, **kwargs):
                result = original_stat(path, *args, **kwargs)
                if path == source:
                    return SimpleNamespace(st_size=2, st_mode=stat.S_IFREG | 0o644)
                return result

            with patch.object(Path, "stat", autospec=True, side_effect=stale_stat):
                summaries = list(iter_repository_summaries(
                    root, max_files=None, max_total_source_bytes=3,
                ))

        self.assertEqual(summaries[0]["analysis"], "source_budget_exceeded")
        self.assertEqual(summaries[0]["source_bytes_read"], 4)
        self.assertEqual(summaries[0]["source_budget_bytes"], 3)

    def test_budget_counts_bytes_read_before_a_source_read_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.py").write_bytes(b"x=")

            with patch.object(
                repository_index, "_read_bounded_source",
                side_effect=repository_index._SourceReadError(OSError("read failed"), 3),
            ):
                summaries = list(iter_repository_summaries(
                    root, max_files=None, max_total_source_bytes=3,
                ))

        self.assertEqual(summaries[0]["analysis"], "unreadable_file")
        self.assertEqual(summaries[0]["source_bytes_read"], 3)
        self.assertTrue(summaries[0]["source_budget_exhausted"])

    def test_total_budget_validates_exact_bounded_integers(self):
        with tempfile.TemporaryDirectory() as directory:
            for budget in (True, -1, 1.5, 10 ** 100):
                with self.subTest(budget=budget), self.assertRaises(ValueError):
                    list(iter_repository_summaries(
                        directory, max_total_source_bytes=budget,
                    ))

    def test_uncapped_default_keeps_the_existing_summary_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "a.py"
            path.write_text("value = 1\n")
            summary = next(iter_repository_summaries(Path(directory)))

        self.assertEqual(summary["analysis"], "python_ast")
        self.assertNotIn("source_bytes_read", summary)
        self.assertNotIn("source_budget_bytes", summary)

    def test_missing_repository_path_does_not_return_synthetic_world(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing-repository"
            with self.assertRaises(FileNotFoundError):
                RepoRPGGenerator.scan_local_directory(str(missing))

    def test_existing_empty_directory_keeps_synthetic_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            world = RepoRPGGenerator.scan_local_directory(directory)
        self.assertEqual(world.repo_name, Path(directory).name)
        self.assertTrue(world.nodes)
        self.assertTrue(all("provenance:synthetic_fallback:no_analyzable_files" in node.tags
                            for node in world.nodes))

    def test_direct_demo_world_is_not_marked_as_a_scan_fallback(self):
        world = RepoRPGGenerator.generate_synthetic_world()

        self.assertTrue(world.nodes)
        self.assertTrue(all("provenance:synthetic_fallback:no_analyzable_files" not in node.tags
                            for node in world.nodes))

    def test_file_path_is_not_treated_as_an_empty_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "module.py"
            file_path.write_text("value = 1\n")
            with self.assertRaises(NotADirectoryError):
                RepoRPGGenerator.scan_local_directory(str(file_path))

    def test_scan_exposes_oversized_file_status_and_limit_override(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "module.py").write_text("value = 1\n")
            limited = RepoRPGGenerator.scan_local_directory(directory, max_file_bytes=4)
            unlimited = RepoRPGGenerator.scan_local_directory(directory, max_file_bytes=None)
        self.assertIn("source_too_large", limited.nodes[0].tags)
        self.assertIn("python_ast", unlimited.nodes[0].tags)

    def test_large_scan_releases_each_summary_after_projecting_its_node(self):
        class Payload:
            pass

        references = []

        def summaries(*args, **kwargs):
            for index in range(64):
                payload = Payload()
                references.append(weakref.ref(payload))
                yield {
                    "path": f"module_{index}.py",
                    "lines_of_code": 1,
                    "complexity": 1.0,
                    "imports": [],
                    "analysis": "python_ast",
                    "unused_payload": payload,
                }
                gc.collect()
                if index:
                    self.assertIsNone(references[index - 1]())

        with tempfile.TemporaryDirectory() as directory:
            with patch("play_anything.adapters.repo_rpg_generator.iter_repository_summaries",
                       side_effect=summaries):
                world = RepoRPGGenerator.scan_local_directory(directory, max_files=None)
        self.assertEqual(len(world.nodes), 64)
        self.assertEqual(len(references), 64)

    def test_large_repository_preserves_import_edges_without_summary_list(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index in range(40):
                dependency = "" if index == 0 else f"import module_{index - 1:02d}\n"
                (root / f"module_{index:02d}.py").write_text(dependency)
            world = RepoRPGGenerator.scan_local_directory(directory, max_files=None)
        self.assertEqual(len(world.nodes), 40)
        self.assertEqual(len(world.edges), 39)
        node_names = {node.node_id: node.name for node in world.nodes}
        self.assertEqual(
            (node_names[world.edges[0].source], node_names[world.edges[0].target]),
            ("module_00.py", "module_01.py"),
        )
