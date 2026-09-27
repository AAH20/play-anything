import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from play_anything.adapters.repository_index import iter_repository_summaries
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
        with patch.object(Path, "read_bytes", side_effect=PermissionError):
            summary = next(iter_repository_summaries(self.root))
        self.assertEqual(summary["analysis"], "unreadable_file")

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
        with sqlite3.connect(cache) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM repository_summaries").fetchone()[0], 1)
            stored = json.loads(db.execute("SELECT summary FROM repository_summaries").fetchone()[0])
            self.assertEqual(stored["lines_of_code"], 2)

    def test_cache_repository_identity_and_deleted_files(self):
        cache = self.root / "index.sqlite"
        self.write("one/a.py", "value = 1\n")
        self.write("two/a.py", "value = 1\n")
        for name in ("one", "two"):
            list(iter_repository_summaries(self.root / name, cache_path=cache))
        with sqlite3.connect(cache) as db:
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
        with sqlite3.connect(cache) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM repository_summaries").fetchone()[0], 1)
            db.execute("DROP TABLE repository_summaries")
