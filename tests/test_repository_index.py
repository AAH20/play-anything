import json
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from play_anything.adapters.repository_index import (
    DEFAULT_MAX_SOURCE_BYTES,
    iter_repository_summaries,
    resolve_python_imports,
)
from play_anything.adapters.repo_rpg_generator import RepoRPGGenerator


class RepositoryIndexTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name, source):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
        return path

    def test_python_metrics_and_dependency_direction(self):
        self.write("b.py", "import a\nif True and False:\n    pass\n")
        self.write("a.py", "value = 1\n")
        world = RepoRPGGenerator.scan_local_directory(str(self.root))
        self.assertEqual([n.name for n in world.nodes], ["a.py", "b.py"])
        self.assertEqual(world.nodes[1].lines_of_code, 3)
        self.assertEqual(world.nodes[1].complexity, 3.0)
        self.assertIn("python_ast", world.nodes[1].tags)
        self.assertEqual([(e.source, e.target, e.relation) for e in world.edges],
                         [("file_00", "file_01", "imports")])

    def test_relative_imports_src_layout_and_external_imports(self):
        self.write("src/pkg/__init__.py", "")
        self.write("src/pkg/helper.py", "VALUE = 1\n")
        self.write("src/pkg/sub/worker.py", "from .. import helper\nimport missing\nfrom ... import helper\n")
        world = RepoRPGGenerator.scan_local_directory(str(self.root))
        names = {node.node_id: node.name for node in world.nodes}
        pairs = {(names[e.source], names[e.target]) for e in world.edges}
        self.assertEqual(pairs, {
            ("src/pkg/helper.py", "src/pkg/sub/worker.py"),
            ("src/pkg/__init__.py", "src/pkg/sub/worker.py"),
        })

    def test_nested_relative_imports_resolve_package_initializers_and_modules(self):
        self.write("pkg/__init__.py", "")
        self.write("pkg/other.py", "VALUE = 1\n")
        self.write("pkg/sub/__init__.py", "from . import leaf\n")
        self.write("pkg/sub/leaf.py", "value = 1\n")
        self.write("pkg/sub/worker.py", "from .. import other\nfrom .leaf import value\n")

        world = RepoRPGGenerator.scan_local_directory(str(self.root))
        names = {node.node_id: node.name for node in world.nodes}
        pairs = {(names[edge.source], names[edge.target]) for edge in world.edges}

        self.assertEqual(pairs, {
            ("pkg/__init__.py", "pkg/sub/worker.py"),
            ("pkg/other.py", "pkg/sub/worker.py"),
            ("pkg/sub/leaf.py", "pkg/sub/__init__.py"),
            ("pkg/sub/leaf.py", "pkg/sub/worker.py"),
        })
        summaries = list(iter_repository_summaries(self.root))
        import_pairs = set(resolve_python_imports(
            summaries, {node.name: node.node_id for node in world.nodes}
        ))
        self.assertEqual(import_pairs, {
            (edge.source, edge.target) for edge in world.edges
        })

    def test_syntax_errors_and_other_languages_are_explicit(self):
        self.write("a.py", "def broken(:\n")
        self.write("view.tsx", "const x = 1;\nconst y = 2;\n")
        summaries = list(iter_repository_summaries(self.root))
        self.assertEqual([s["analysis"] for s in summaries],
                         ["python_parse_error", "unparsed_language"])
        self.assertEqual(summaries[1]["lines_of_code"], 2)
        self.assertEqual(RepoRPGGenerator.scan_local_directory(str(self.root)).edges, [])

    def test_encoding_cookie(self):
        (self.root / "encoded.py").write_bytes(b"# coding: latin-1\nname = '\xe9'\n")
        self.assertEqual(next(iter_repository_summaries(self.root))["analysis"], "python_ast")

    def test_unreadable_file(self):
        self.write("a.py", "value = 1")
        with patch("play_anything.adapters.repository_index.os.open",
                   side_effect=PermissionError):
            summary = next(iter_repository_summaries(self.root))
        self.assertEqual(summary["analysis"], "unreadable_file")

    def test_oversized_file_is_reported_without_reading_its_contents(self):
        source = self.root / "large.py"
        source.write_bytes(b"x" * (DEFAULT_MAX_SOURCE_BYTES + 1))
        with patch.object(Path, "read_bytes", side_effect=AssertionError("full read")), \
                patch("play_anything.adapters.repository_index.os.open",
                      side_effect=AssertionError("source opened")):
            summary = next(iter_repository_summaries(self.root))
        self.assertEqual(summary["analysis"], "source_too_large")
        self.assertEqual(summary["lines_of_code"], 0)
        self.assertEqual(summary["imports"], [])

    def test_source_size_limit_can_be_overridden_or_disabled(self):
        self.write("a.py", "value = 1\n")
        limited = next(iter_repository_summaries(self.root, max_file_bytes=4))
        unlimited = next(iter_repository_summaries(self.root, max_file_bytes=None))
        self.assertEqual(limited["analysis"], "source_too_large")
        self.assertEqual(unlimited["analysis"], "python_ast")

    def test_directory_walk_errors_are_propagated(self):
        def fail_during_walk(*args, **kwargs):
            kwargs["onerror"](PermissionError("directory denied"))
            return iter(())

        with patch("play_anything.adapters.repository_index.os.walk",
                   side_effect=fail_during_walk):
            with self.assertRaisesRegex(PermissionError, "directory denied"):
                list(iter_repository_summaries(self.root))

    def test_invalid_source_size_limits_are_rejected(self):
        for invalid in (0, -1, True, 1.5):
            with self.assertRaises(ValueError):
                list(iter_repository_summaries(self.root, max_file_bytes=invalid))

    def test_order_limit_exclusions_and_empty_fallback(self):
        self.write("z.py", "")
        self.write("a.py", "")
        self.write(".git/hidden.py", "")
        self.write("node_modules/hidden.js", "")
        self.assertEqual([s["path"] for s in iter_repository_summaries(self.root, 1)], ["a.py"])
        self.assertEqual([s["path"] for s in iter_repository_summaries(self.root, None)], ["a.py", "z.py"])
        empty = self.root / "empty"
        empty.mkdir()
        self.assertTrue(RepoRPGGenerator.scan_local_directory(str(empty)).nodes)
        for invalid in (0, -1, True, 1.5):
            with self.assertRaises(ValueError):
                list(iter_repository_summaries(self.root, invalid))

    def test_dot_prefixed_source_files_are_excluded(self):
        self.write("visible.py", "value = 1\n")
        self.write(".secret.py", "token = 'private'\n")
        self.write("config/.private.ts", "export const key = 'private';\n")
        self.assertEqual(
            [summary["path"] for summary in iter_repository_summaries(self.root, None)],
            ["visible.py"],
        )

    def test_default_limit_is_preserved(self):
        for index in range(51):
            self.write(f"{index:02d}.py", "")
        self.assertEqual(len(list(iter_repository_summaries(self.root))), 50)

    def test_symlink_file_is_skipped(self):
        self.write("real.py", "")
        try:
            (self.root / "alias.py").symlink_to(self.root / "real.py")
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks unavailable")
        self.assertEqual([s["path"] for s in iter_repository_summaries(self.root)], ["real.py"])

    @unittest.skipUnless(hasattr(os, "mkfifo"), "named pipes are unavailable")
    def test_non_regular_source_is_not_opened_and_is_reported_unreadable(self):
        fifo = self.root / "blocked.py"
        os.mkfifo(fifo)

        with patch("play_anything.adapters.repository_index._read_bounded_source",
                   side_effect=AssertionError("non-regular source must not be opened")) as read_source:
            summaries = list(iter_repository_summaries(
                self.root, max_total_source_bytes=1, include_source_metrics=True))

        read_source.assert_not_called()
        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0]["path"], "blocked.py")
        self.assertEqual(summaries[0]["analysis"], "unreadable_file")
        self.assertEqual(summaries[0]["source_bytes_read"], 0)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "named pipes are unavailable")
    def test_fifo_replacement_after_stat_is_rejected_without_blocking(self):
        fifo = self.root / "blocked.py"
        os.mkfifo(fifo)
        regular = self.write("regular.py", "value = 1\n")
        regular_stat = regular.stat()
        real_stat = Path.stat

        def report_regular_snapshot(path, *args, **kwargs):
            if path == fifo:
                return regular_stat
            return real_stat(path, *args, **kwargs)

        with patch.object(Path, "stat", report_regular_snapshot):
            summaries = list(iter_repository_summaries(self.root, max_files=None))

        by_path = {summary["path"]: summary for summary in summaries}
        self.assertEqual(by_path["blocked.py"]["analysis"], "unreadable_file")
        self.assertEqual(by_path["regular.py"]["analysis"], "python_ast")

    def test_cache_hit_content_invalidation_and_eviction(self):
        source = self.write("a.py", "value = 1\n")
        cache = self.root / "index.sqlite"
        def scan():
            return list(iter_repository_summaries(self.root, cache_path=cache, cache_max_entries=1))
        original = scan()
        with patch("play_anything.adapters.repository_index.ast.parse", side_effect=AssertionError("cache missed")):
            self.assertEqual(scan(), original)
        source.write_text("if True:\n    value = 2\n")
        self.assertEqual(scan()[0]["complexity"], 2.0)
        with closing(sqlite3.connect(cache)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM repository_summaries").fetchone()[0], 1)
            stored = json.loads(db.execute("SELECT summary FROM repository_summaries").fetchone()[0])
            self.assertEqual(stored["lines_of_code"], 2)

    def test_cache_writes_are_batched_without_holding_locks_across_yields(self):
        for index in range(100):
            self.write(f"{index:03d}.py", f"value = {index}\n")
        cache = self.root / "index.sqlite"
        real_connect = sqlite3.connect
        commit_calls = []

        class CountingConnection(sqlite3.Connection):
            def commit(self):
                commit_calls.append(None)
                return super().commit()

        def connect_counted(*args, **kwargs):
            kwargs["factory"] = CountingConnection
            return real_connect(*args, **kwargs)

        with patch("play_anything.adapters.repository_index.sqlite3.connect",
                   side_effect=connect_counted):
            iterator = iter_repository_summaries(self.root, None, cache_path=cache)
            next(iterator)
            # A separate writer can proceed while the lazy iterator is suspended.
            with closing(real_connect(cache)) as other:
                other.execute("CREATE TABLE external_probe (value INTEGER)")
                other.commit()
            list(iterator)

        self.assertEqual(len(commit_calls), 3)  # setup, one 64-row flush, final 36 rows
        with closing(real_connect(cache)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM repository_summaries").fetchone()[0], 100)

    def test_cache_flushes_pending_rows_when_iterator_is_closed_early(self):
        for index in range(4):
            self.write(f"{index}.py", f"value = {index}\n")
        cache = self.root / "index.sqlite"
        iterator = iter_repository_summaries(self.root, None, cache_path=cache)
        next(iterator)
        iterator.close()
        with closing(sqlite3.connect(cache)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM repository_summaries").fetchone()[0], 1)

    def test_cache_flushes_pending_rows_when_traversal_fails(self):
        self.write("a.py", "value = 1\n")
        cache = self.root / "index.sqlite"

        def fail_after_one_file(root, *, onerror):
            yield str(root), [], ["a.py"]
            onerror(PermissionError("subdirectory denied"))

        with patch("play_anything.adapters.repository_index.os.walk",
                   side_effect=fail_after_one_file):
            iterator = iter_repository_summaries(self.root, None, cache_path=cache)
            next(iterator)
            with self.assertRaisesRegex(PermissionError, "subdirectory denied"):
                next(iterator)
        with closing(sqlite3.connect(cache)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM repository_summaries").fetchone()[0], 1)

    def test_cache_limit_is_enforced_at_each_batch_commit(self):
        for index in range(70):
            self.write(f"{index:03d}.py", f"value = {index}\n")
        cache = self.root / "index.sqlite"
        list(iter_repository_summaries(
            self.root, None, cache_path=cache, cache_max_entries=7
        ))
        with closing(sqlite3.connect(cache)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM repository_summaries").fetchone()[0], 7)

    def test_cache_repository_identity_and_deleted_files(self):
        cache = self.root / "index.sqlite"
        self.write("one/a.py", "value = 1\n")
        self.write("two/a.py", "value = 1\n")
        for name in ("one", "two"):
            list(iter_repository_summaries(self.root / name, cache_path=cache))
        with closing(sqlite3.connect(cache)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM repository_summaries").fetchone()[0], 2)
        (self.root / "one/a.py").unlink()
        self.assertEqual(list(iter_repository_summaries(self.root / "one", cache_path=cache)), [])

    def test_iteration_is_lazy_and_close_releases_cache(self):
        self.write("a.py", "")
        self.write("b.py", "")
        cache = self.root / "index.sqlite"
        iterator = iter_repository_summaries(self.root, cache_path=cache)
        self.assertFalse(cache.exists())
        next(iterator)
        iterator.close()
        with closing(sqlite3.connect(cache)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM repository_summaries").fetchone()[0], 1)
            db.execute("DROP TABLE repository_summaries")
            db.commit()
