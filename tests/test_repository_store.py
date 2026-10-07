import json
from contextlib import closing
import gc
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import weakref

from play_anything.adapters.repository_store import SQLiteRepositoryStore
from play_anything.adapters.repository_index import iter_repository_summaries, resolve_python_imports


class RepositoryStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.root = base / "repo"
        self.root.mkdir()
        self.db_path = base / "index.sqlite3"

    def write(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_build_paginates_literal_search_and_reports_partial_status(self):
        self.write("src/pkg/__init__.py", "from . import worker\n")
        self.write("src/pkg/worker.py", "import json\n")
        self.write("src/consumer.py", "from pkg.worker import run\n")
        self.write("notes.md", "plain notes\n")

        with SQLiteRepositoryStore(self.db_path) as store:
            result = store.rebuild(self.root, max_files=None)
            self.assertEqual(result["file_count"], 4)
            self.assertEqual([row["path"] for row in store.files(self.root, limit=2)],
                             ["notes.md", "src/consumer.py"])
            self.assertEqual([row["path"] for row in store.files(self.root, limit=2, offset=2)],
                             ["src/pkg/__init__.py", "src/pkg/worker.py"])
            self.assertEqual([row["path"] for row in store.search_files(
                self.root, "consumer", limit=10)], ["src/consumer.py"])
            edges = store.imports(self.root)
            self.assertEqual(edges, [
                {"dependency": "src/pkg/worker.py", "importer": "src/consumer.py"},
                {"dependency": "src/pkg/worker.py", "importer": "src/pkg/__init__.py"},
            ])
            self.assertEqual(store.dependencies(self.root, "src/consumer.py"),
                             ["src/pkg/worker.py"])
            status = store.status(self.root)
            self.assertEqual(status["file_count"], 4)
            self.assertTrue(status["imports_partial"])
            self.assertEqual(status["max_file_bytes"], 2 * 1024 * 1024)

    def test_queries_reject_nonobject_or_mismatched_stored_summaries(self):
        self.write("a.py", "value = 1\n")
        with SQLiteRepositoryStore(self.db_path) as store:
            original = store.rebuild(self.root, max_files=None)

        with closing(sqlite3.connect(self.db_path)) as db:
            db.execute("UPDATE pa_repo_files SET summary_json = '[]'")
            db.commit()

        with SQLiteRepositoryStore(self.db_path, read_only=True) as store:
            for query in (
                lambda: store.files(self.root),
                lambda: store.search_files(self.root, "a.py"),
                lambda: store.graph_page(self.root),
            ):
                with self.subTest(query=query), self.assertRaisesRegex(
                        ValueError, "stored summary.*JSON object"):
                    query()
            self.assertEqual(store.status(self.root)["generation"], original["generation"])

        with closing(sqlite3.connect(self.db_path)) as db:
            db.execute("UPDATE pa_repo_files SET summary_json = ?", (
                json.dumps({"path": "other.py", "lines_of_code": 1,
                            "complexity": 1.0, "imports": [], "analysis": "python_ast"}),))
            db.commit()

        with SQLiteRepositoryStore(self.db_path, read_only=True) as store:
            with self.assertRaisesRegex(ValueError, "does not match indexed"):
                store.graph_page(self.root)
            self.assertEqual(store.status(self.root)["generation"], original["generation"])

    @unittest.skipUnless(os.name == "posix", "backslash is an ordinary POSIX filename character")
    def test_unportable_filename_error_is_escaped_and_preserves_active_generation(self):
        self.write("valid.py", "value = 1\n")
        with SQLiteRepositoryStore(self.db_path) as store:
            before = store.rebuild(self.root, max_files=None)
            bad_name = "bad\\" + "x" * 180 + "\nname.py"
            self.write(bad_name, "value = 2\n")

            with self.assertRaises(ValueError) as raised:
                store.rebuild(self.root, max_files=None)

            message = str(raised.exception)
            self.assertIn("path must be a non-empty repository-relative POSIX path", message)
            self.assertIn(ascii(bad_name[:120] + "…"), message)
            self.assertNotIn("\n", message)
            self.assertLess(len(message), 600)
            after = store.status(self.root)
            self.assertEqual(after["generation"], before["generation"])
            self.assertEqual([row["path"] for row in store.files(self.root)], ["valid.py"])

    def test_missing_namespace_has_no_phantom_edges_and_roots_are_isolated(self):
        self.write("a.py", "import b\n")
        other = self.root.parent / "other"
        other.mkdir()
        (other / "a.py").write_text("import b\n", encoding="utf-8")
        (other / "b.py").write_text("value = 1\n", encoding="utf-8")

        with SQLiteRepositoryStore(self.db_path) as store:
            store.rebuild(self.root)
            store.rebuild(other)
            self.assertEqual(store.imports(self.root), [])
            self.assertEqual(store.imports(other), [
                {"dependency": "b.py", "importer": "a.py"},
            ])
            self.assertEqual(store.status(self.root)["file_count"], 1)
            self.assertEqual(store.status(other)["file_count"], 2)

    def test_ambiguous_python_module_is_not_resolved(self):
        self.write("importer.py", "import thing\n")
        self.write("thing.py", "value = 1\n")
        self.write("src/thing.py", "value = 2\n")
        with SQLiteRepositoryStore(self.db_path) as store:
            store.rebuild(self.root, max_files=None)
            self.assertEqual(store.imports(self.root), [])

    def test_graph_page_counts_hubs_self_edges_and_filtered_incidence(self):
        for index in range(80):
            self.write(f"module_{index:03}.py", "value = 1\n")
        self.write("zz_isolated.py", "value = 2\n")

        with SQLiteRepositoryStore(self.db_path) as store:
            status = store.rebuild(self.root, max_files=None)
            generation = status["generation"]
            edges = [
                (status["root"], generation, f"module_{source:03}.py", f"module_{importer:03}.py")
                for source in range(80) for importer in range(80)
            ]
            store._db.executemany(
                "INSERT INTO pa_repo_import_edges VALUES (?, ?, ?, ?)", edges
            )
            store._db.commit()

            statements = []
            store._db.set_trace_callback(statements.append)
            try:
                page = store.graph_page(self.root, limit=3, max_edges=4)
            finally:
                store._db.set_trace_callback(None)

            coverage = page["coverage"]
            self.assertEqual(coverage["total_import_edges"], 80 * 80)
            self.assertEqual(coverage["returned_page_edges"], 4)
            self.assertEqual(coverage["omitted_page_edges"], 3 * 3 - 4)
            self.assertEqual(coverage["omitted_cross_page_edges"], 80 * 3 + 80 * 3 - 2 * 3 * 3)

            filtered = store.graph_page(self.root, limit=10, search="module_000")
            self.assertEqual(filtered["coverage"]["matching_nodes"], 1)
            self.assertEqual(filtered["coverage"]["omitted_page_edges"], 0)
            self.assertEqual(filtered["coverage"]["omitted_cross_page_edges"], 80 * 2 - 2)

            isolated = store.graph_page(self.root, limit=10, search="zz_isolated.py")
            self.assertEqual(isolated["coverage"]["returned_nodes"], 1)
            self.assertEqual(isolated["edges"], [])
            self.assertEqual(isolated["coverage"]["omitted_page_edges"], 0)
            self.assertEqual(isolated["coverage"]["omitted_cross_page_edges"], 0)

            incident_sql = next(
                statement for statement in statements
                if "CROSS JOIN pa_repo_import_edges e" in statement and "UNION ALL" in statement
            )
            plan = [row[3] for row in store._db.execute(
                "EXPLAIN QUERY PLAN " + incident_sql
            ).fetchall()]
            self.assertFalse(any(detail.startswith("SCAN e") for detail in plan), plan)
            self.assertTrue(any("importer=?" in detail for detail in plan), plan)
            self.assertTrue(any("dependency=?" in detail for detail in plan), plan)

    def test_file_cap_and_source_cap_are_visible_in_persisted_status(self):
        self.write("a.py", "x = 1\n")
        self.write("b.py", "x = 2\n")
        self.write("c.py", "x = 'long'\n")

        with SQLiteRepositoryStore(self.db_path) as store:
            store.rebuild(self.root, max_files=2, max_file_bytes=4)
            status = store.status(self.root)
            self.assertEqual(status["file_count"], 2)
            self.assertEqual(status["max_files"], 2)
            self.assertEqual(status["max_file_bytes"], 4)
            self.assertTrue(status["truncated"])
            self.assertTrue(status["partial"])
            self.assertTrue(any(row["analysis"] == "source_too_large"
                                for row in store.files(self.root, limit=10)))

    def test_total_source_budget_is_persisted_and_exposed_in_graph_coverage(self):
        self.write("a.py", "x=1\n")
        self.write("b.py", "y=2\n")
        self.write("c.py", "z=3\n")
        with SQLiteRepositoryStore(self.db_path) as store:
            result = store.rebuild(self.root, max_files=None, max_total_source_bytes=6)
            status = store.status(self.root)
            page = store.graph_page(self.root, limit=10)

        self.assertEqual(result["max_total_source_bytes"], 6)
        self.assertEqual(result["source_bytes_read"], 4)
        self.assertEqual(result["source_budget_exceeded_files"], 2)
        self.assertTrue(result["source_budget_exhausted"])
        self.assertEqual(status["analysis_counts"]["source_budget_exceeded"], 2)
        self.assertEqual(status["source_bytes_read"], page["coverage"]["source_bytes_read"])
        self.assertEqual(page["coverage"]["source_budget_bytes"], 6)
        self.assertEqual(page["coverage"]["source_budget_exceeded_files"], 2)
        self.assertTrue(page["coverage"]["source_budget_exhausted"])
        self.assertTrue(page["coverage"]["source_partial"])
        self.assertTrue(page["analysis"]["source_budget_exhausted"])

    def test_graph_page_keeps_large_optional_metrics_exact_for_json_consumers(self):
        self.write("a.py", "x = 1\n")
        safe = (1 << 53) - 1
        values = (safe, safe + 1, sys.maxsize - 1)
        with SQLiteRepositoryStore(self.db_path) as store:
            store.rebuild(self.root, max_files=safe, max_file_bytes=safe,
                          max_total_source_bytes=safe)
            root_key = str(self.root.resolve())
            for value in values:
                with closing(sqlite3.connect(self.db_path)) as db:
                    generation = store.status(self.root)["generation"]
                    db.execute("UPDATE pa_repo_generations SET max_files = ?, max_file_bytes = ?, "
                               "max_total_source_bytes = ?, source_bytes_read = ?, "
                               "source_budget_exceeded_files = ? WHERE root = ? AND generation = ?",
                               (value, value, value, value, value, root_key, generation))
                    db.commit()

                status = store.status(self.root)
                self.assertEqual(status["max_files"], value)
                self.assertEqual(status["max_file_bytes"], value)
                self.assertEqual(status["source_bytes_read"], value)
                page = json.loads(json.dumps(store.graph_page(self.root)))
                for section, fields in {
                    "analysis": ("file_limit", "max_file_bytes", "source_bytes_read",
                                 "source_budget_bytes", "source_budget_exceeded_files"),
                    "coverage": ("max_files", "max_file_bytes", "max_total_source_bytes",
                                 "source_budget_bytes", "source_bytes_read",
                                 "source_budget_exceeded_files"),
                }.items():
                    record = page[section]
                    for field in fields:
                        if value <= safe:
                            self.assertEqual(record[field], value, (section, field, value))
                            self.assertNotIn(field + "_exact", record)
                        else:
                            self.assertIsNone(record[field], (section, field, value))
                            self.assertEqual(record[field + "_exact"], str(value),
                                             (section, field, value))
        self.assertFalse(page["coverage"]["complete"])

    def test_uncapped_rebuild_still_reports_actual_source_bytes_without_exhaustion(self):
        self.write("a.py", "x=1\n")
        self.write("notes.md", "notes\n")
        with SQLiteRepositoryStore(self.db_path) as store:
            status = store.rebuild(self.root, max_files=None)

        self.assertEqual(status["source_bytes_read"], 10)
        self.assertIsNone(status["source_budget_bytes"])
        self.assertIsNone(status["max_total_source_bytes"])
        self.assertFalse(status["source_budget_exhausted"])
        self.assertEqual(status["source_budget_exceeded_files"], 0)

    def test_exact_source_budget_fill_without_exclusions_is_not_partial(self):
        self.write("a.py", "x=1\n")
        self.write("b.py", "y\n")
        with SQLiteRepositoryStore(self.db_path) as store:
            status = store.rebuild(self.root, max_files=None, max_total_source_bytes=6)
            page = store.graph_page(self.root, limit=10)

        self.assertEqual(status["source_bytes_read"], 6)
        self.assertTrue(status["source_budget_exhausted"])
        self.assertEqual(status["source_budget_exceeded_files"], 0)
        self.assertFalse(status["partial"])
        self.assertTrue(page["coverage"]["complete"])
        self.assertFalse(page["coverage"]["source_partial"])

    def test_zero_budget_parses_empty_sources_and_records_nonempty_exclusions(self):
        self.write("a-empty.py", "")
        self.write("b-nonempty.py", "x=1\n")
        with SQLiteRepositoryStore(self.db_path) as store:
            status = store.rebuild(self.root, max_files=None, max_total_source_bytes=0)
            rows = {row["path"]: row for row in store.files(self.root, limit=10)}

        self.assertEqual(status["source_bytes_read"], 0)
        self.assertEqual(status["source_budget_exceeded_files"], 1)
        self.assertTrue(status["source_budget_exhausted"])
        self.assertEqual(rows["a-empty.py"]["analysis"], "python_ast")
        self.assertEqual(rows["b-nonempty.py"]["analysis"], "source_budget_exceeded")

    def test_growth_sentinel_is_counted_and_old_active_generation_survives_failure(self):
        self.write("a.py", "x=1\n")
        with SQLiteRepositoryStore(self.db_path) as store:
            old = store.rebuild(self.root, max_files=None, max_total_source_bytes=4)
            original_read = __import__("play_anything.adapters.repository_index",
                                       fromlist=["_read_bounded_source"])._read_bounded_source

            def grew_after_stat(path, limit):
                content = original_read(path, limit)
                return content + b"x" if path.name == "a.py" else content

            with patch("play_anything.adapters.repository_index._read_bounded_source",
                       side_effect=grew_after_stat):
                changed = store.rebuild(self.root, max_files=None,
                                         max_total_source_bytes=4)

            self.assertEqual(changed["source_bytes_read"], 5)
            self.assertEqual(changed["source_budget_exceeded_files"], 1)
            self.assertTrue(changed["source_budget_exhausted"])
            self.assertNotEqual(changed["generation"], old["generation"])

            def broken_summaries(*args, **kwargs):
                yield {"path": "stage.py", "analysis": "python_ast", "imports": []}
                raise OSError("injected traversal failure")

            with patch("play_anything.adapters.repository_store.iter_repository_summaries",
                       side_effect=broken_summaries):
                with self.assertRaisesRegex(OSError, "injected traversal"):
                    store.rebuild(self.root, max_files=None, max_total_source_bytes=1)
            self.assertEqual(store.status(self.root)["generation"], changed["generation"])
            self.assertEqual(store.status(self.root)["source_bytes_read"], 5)

    def test_legacy_generation_schema_migrates_budget_columns_without_losing_rows(self):
        root_key = str(self.root.resolve())
        generation = "legacy-generation"
        with closing(sqlite3.connect(self.db_path)) as legacy:
            legacy.execute("CREATE TABLE pa_repo_generations ("
                           "root TEXT NOT NULL, generation TEXT NOT NULL, max_files INTEGER, "
                           "max_file_bytes INTEGER, file_count INTEGER NOT NULL DEFAULT 0, "
                           "truncated INTEGER NOT NULL DEFAULT 0, "
                           "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                           "PRIMARY KEY(root, generation))")
            legacy.execute("CREATE TABLE pa_repo_active (root TEXT PRIMARY KEY, generation TEXT NOT NULL)")
            legacy.execute("CREATE TABLE pa_repo_files ("
                           "root TEXT NOT NULL, generation TEXT NOT NULL, path TEXT NOT NULL, "
                           "analysis TEXT NOT NULL, summary_json TEXT NOT NULL, "
                           "PRIMARY KEY(root,generation,path))")
            legacy.execute("INSERT INTO pa_repo_generations(root,generation,max_files,max_file_bytes,file_count,truncated) "
                           "VALUES(?,?,?,?,?,?)", (root_key, generation, 3, 10, 1, 0))
            legacy.execute("INSERT INTO pa_repo_files(root,generation,path,analysis,summary_json) "
                           "VALUES(?,?,?,?,?)", (root_key, generation, "src/legacy.py", "python_ast",
                                                  json.dumps({"path": "src/legacy.py", "analysis": "python_ast"})))
            legacy.execute("INSERT INTO pa_repo_active(root,generation) VALUES(?,?)",
                           (root_key, generation))
            legacy.commit()

        with SQLiteRepositoryStore(self.db_path) as store:
            status = store.status(self.root)
        self.assertEqual(status["generation"], generation)
        self.assertEqual(status["max_files"], 3)
        self.assertIsNone(status["max_total_source_bytes"])
        self.assertEqual(status["file_count"], 1)
        self.assertFalse(status["source_metrics_available"])
        self.assertIsNone(status["source_bytes_read"])
        self.assertIsNone(status["source_budget_exhausted"])
        self.assertIsNone(status["source_budget_exceeded_files"])
        with SQLiteRepositoryStore(self.db_path, read_only=True) as store:
            migrated = store.status(self.root)
            self.assertEqual(migrated["generation"], generation)
            self.assertFalse(migrated["source_metrics_available"])
            self.assertEqual(store.files(self.root), [{"path": "src/legacy.py", "analysis": "python_ast"}])

    def test_intermediate_generation_migration_retains_known_cap_but_unknown_metrics(self):
        root_key = str(self.root.resolve())
        generation = "intermediate-generation"
        large_cap = sys.maxsize - 1
        with closing(sqlite3.connect(self.db_path)) as legacy:
            legacy.execute("CREATE TABLE pa_repo_generations ("
                           "root TEXT NOT NULL, generation TEXT NOT NULL, max_files INTEGER, "
                           "max_file_bytes INTEGER, max_total_source_bytes INTEGER, "
                           "source_bytes_read INTEGER NOT NULL DEFAULT 0, "
                           "source_budget_exhausted INTEGER NOT NULL DEFAULT 0, "
                           "source_budget_exceeded_files INTEGER NOT NULL DEFAULT 0, "
                           "file_count INTEGER NOT NULL DEFAULT 0, truncated INTEGER NOT NULL DEFAULT 0, "
                           "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                           "PRIMARY KEY(root,generation))")
            legacy.execute("CREATE TABLE pa_repo_active (root TEXT PRIMARY KEY, generation TEXT NOT NULL)")
            legacy.execute("CREATE TABLE pa_repo_files ("
                           "root TEXT NOT NULL, generation TEXT NOT NULL, path TEXT NOT NULL, "
                           "analysis TEXT NOT NULL, summary_json TEXT NOT NULL, "
                           "PRIMARY KEY(root,generation,path))")
            legacy.execute("CREATE TABLE pa_repo_modules ("
                           "root TEXT NOT NULL, generation TEXT NOT NULL, module TEXT NOT NULL, "
                           "path TEXT NOT NULL, PRIMARY KEY(root,generation,module,path))")
            legacy.execute("CREATE TABLE pa_repo_import_edges ("
                           "root TEXT NOT NULL, generation TEXT NOT NULL, dependency TEXT NOT NULL, "
                           "importer TEXT NOT NULL, PRIMARY KEY(root,generation,dependency,importer))")
            legacy.execute("INSERT INTO pa_repo_generations(root,generation,max_files,max_file_bytes,"
                           "max_total_source_bytes,source_bytes_read,source_budget_exhausted,"
                           "source_budget_exceeded_files,file_count,truncated) "
                           "VALUES(?,?,?,?,?,?,?,?,?,?)",
                           (root_key, generation, 10, 4096, large_cap, 0, 0, 0, 2, 0))
            legacy.execute("INSERT INTO pa_repo_active(root,generation) VALUES(?,?)",
                           (root_key, generation))
            for path in ("a.py", "b.py"):
                legacy.execute("INSERT INTO pa_repo_files VALUES(?,?,?,?,?)",
                               (root_key, generation, path, "python_ast",
                                json.dumps({"path": path, "analysis": "python_ast"})))
            legacy.executemany("INSERT INTO pa_repo_modules VALUES(?,?,?,?)", [
                (root_key, generation, "a", "a.py"),
                (root_key, generation, "b", "b.py"),
            ])
            legacy.execute("INSERT INTO pa_repo_import_edges VALUES(?,?,?,?)",
                           (root_key, generation, "b.py", "a.py"))
            legacy.commit()

        with SQLiteRepositoryStore(self.db_path) as store:
            status = store.status(self.root)
            self.assertEqual(status["max_total_source_bytes"], large_cap)
            self.assertFalse(status["source_metrics_available"])
            self.assertIsNone(status["source_bytes_read"])
            self.assertIsNone(status["source_budget_bytes"])
            self.assertIsNone(status["source_budget_exhausted"])
            self.assertIsNone(status["source_budget_exceeded_files"])
            self.assertEqual([row["path"] for row in store.files(self.root)], ["a.py", "b.py"])
            self.assertEqual(store.imports(self.root), [{"dependency": "b.py", "importer": "a.py"}])
            page = store.graph_page(self.root)
            self.assertEqual(page["coverage"]["max_total_source_bytes"], None)
            self.assertEqual(page["coverage"]["max_total_source_bytes_exact"], str(large_cap))
            self.assertFalse(page["coverage"]["source_metrics_available"])
            self.assertIsNone(page["coverage"]["source_budget_bytes"])
            self.assertNotIn("source_budget_bytes_exact", page["coverage"])
            self.assertIsNone(page["coverage"]["source_bytes_read"])
            self.assertFalse(page["analysis"]["source_metrics_available"])
            self.assertIsNone(page["analysis"]["source_budget_bytes"])
            self.assertNotIn("source_budget_bytes_exact", page["analysis"])
            self.assertEqual(page["edges"], [{"source": "file:a.py", "target": "file:b.py",
                                               "relation": "imports", "confidence": "parsed"}])

    def test_invalid_paths_limits_and_database_inside_root_are_rejected(self):
        self.write("a.py", "x = 1\n")
        with SQLiteRepositoryStore(self.root / "nested.sqlite3") as store:
            with self.assertRaises(ValueError):
                store.rebuild(self.root)
        with SQLiteRepositoryStore(self.db_path) as store:
            with self.assertRaises(ValueError):
                store.files(self.root, limit=True)
            with self.assertRaises(ValueError):
                store.files(self.root, limit=1001)
            with self.assertRaises(ValueError):
                store.files(self.root, offset=-1)
            with self.assertRaises(ValueError):
                store.files(self.root, offset=1 << 63)
            with self.assertRaises(ValueError):
                store.dependencies(self.root, "../outside.py")
            with self.assertRaises(ValueError):
                store.rebuild(self.root, max_files=1 << 63)
            with self.assertRaises(ValueError):
                store.rebuild(self.root, max_file_bytes=1 << 63)
            for invalid in (True, -1, sys.maxsize, 1.5):
                with self.subTest(max_total_source_bytes=invalid), self.assertRaises(ValueError):
                    store.rebuild(self.root, max_total_source_bytes=invalid)

    def test_failed_rebuild_keeps_previous_active_generation(self):
        self.write("old.py", "x = 1\n")
        with SQLiteRepositoryStore(self.db_path) as store:
            store.rebuild(self.root)
            old_status = store.status(self.root)
            self.write("new.py", "y = 2\n")

            def broken_summaries(*args, **kwargs):
                for index in range(70):
                    yield {"path": f"stage_{index:03}.py", "lines_of_code": 1,
                           "complexity": 1.0, "imports": [], "analysis": "python_ast"}
                raise OSError("injected traversal failure")

            with patch("play_anything.adapters.repository_store.iter_repository_summaries",
                       side_effect=broken_summaries):
                with self.assertRaisesRegex(OSError, "injected traversal"):
                    store.rebuild(self.root, max_files=None)

            self.assertEqual(store.status(self.root)["generation"], old_status["generation"])
            self.assertEqual([row["path"] for row in store.files(self.root, limit=10)], ["old.py"])
            with closing(sqlite3.connect(self.db_path)) as check:
                self.assertEqual(check.execute(
                    "SELECT COUNT(*) FROM pa_repo_generations WHERE root = ? AND generation != ?",
                    (str(self.root.resolve()), old_status["generation"])).fetchone()[0], 0)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "named pipes are unavailable")
    def test_fifo_source_is_bounded_and_marks_store_partial(self):
        os.mkfifo(self.root / "blocked.py")

        with SQLiteRepositoryStore(self.db_path) as store:
            result = store.rebuild(self.root, max_files=None, max_total_source_bytes=1)
            status = store.status(self.root)
            files = store.files(self.root, limit=10)

        self.assertEqual(result["analysis_counts"]["unreadable_file"], 1)
        self.assertTrue(status["partial"])
        self.assertEqual([(row["path"], row["analysis"]) for row in files],
                         [("blocked.py", "unreadable_file")])

    def test_store_import_edges_match_streaming_resolver_and_excludes_generated_dirs(self):
        self.write("src/pkg/__init__.py", "from . import worker\n")
        self.write("src/pkg/worker.py", "import json\n")
        self.write("src/client.py", "from pkg.worker import run\n")
        self.write("site-dist/bundle.js", "generated bundle")
        summaries = list(iter_repository_summaries(self.root, max_files=None))
        node_ids = {summary["path"]: summary["path"] for summary in summaries}
        expected = sorted({(dependency, importer) for dependency, importer in
                           resolve_python_imports(summaries, node_ids)})

        with SQLiteRepositoryStore(self.db_path) as store:
            store.rebuild(self.root, max_files=None)
            observed = [(edge["dependency"], edge["importer"])
                        for edge in store.imports(self.root)]
            paths = [row["path"] for row in store.files(self.root, limit=20)]
        self.assertEqual(observed, expected)
        self.assertNotIn("site-dist/bundle.js", paths)

    def test_file_cap_exactly_at_end_is_not_marked_truncated(self):
        self.write("a.py", "x = 1\n")
        self.write("b.py", "x = 2\n")
        with SQLiteRepositoryStore(self.db_path) as store:
            status = store.rebuild(self.root, max_files=2)
        self.assertEqual(status["file_count"], 2)
        self.assertFalse(status["truncated"])

    def test_import_edge_batches_resolve_many_files(self):
        self.write("base.py", "value = 1\n")
        for index in range(70):
            self.write(f"client_{index:03}.py", "import base\n")
        with SQLiteRepositoryStore(self.db_path) as store:
            status = store.rebuild(self.root, max_files=None)
            edges = store.imports(self.root, limit=100)
        self.assertEqual(status["import_edge_count"], 70)
        self.assertEqual(len(edges), 70)
        self.assertEqual(edges[0], {"dependency": "base.py", "importer": "client_000.py"})

    def test_preexisting_unrelated_tables_survive_and_store_closes_context(self):
        db = sqlite3.connect(self.db_path)
        db.execute("CREATE TABLE user_data(value TEXT)")
        db.execute("INSERT INTO user_data VALUES ('keep')")
        db.commit()
        db.close()
        self.write("a.py", "x = 1\n")
        store = SQLiteRepositoryStore(self.db_path)
        with store:
            store.rebuild(self.root)
        with closing(sqlite3.connect(self.db_path)) as check:
            self.assertEqual(check.execute("SELECT value FROM user_data").fetchone()[0], "keep")
        self.assertTrue(store.closed)

    def test_read_only_queries_do_not_scan_or_modify_valid_database(self):
        self.write("a.py", "import b\n")
        self.write("b.py", "value = 1\n")
        with SQLiteRepositoryStore(self.db_path) as store:
            expected_status = store.rebuild(self.root, max_files=None)
            expected_files = store.files(self.root)
            expected_imports = store.imports(self.root)
        original_bytes = self.db_path.read_bytes()
        original_stat = self.db_path.stat()

        with patch("play_anything.adapters.repository_store.iter_repository_summaries",
                   side_effect=AssertionError("read-only queries must not scan source")):
            with SQLiteRepositoryStore(self.db_path, read_only=True) as store:
                self.assertEqual(store.status(self.root), expected_status)
                self.assertEqual(store.files(self.root), expected_files)
                self.assertEqual(store.imports(self.root), expected_imports)
                with self.assertRaisesRegex(ValueError, "read-only"):
                    store.rebuild(self.root)
                with self.assertRaisesRegex(sqlite3.OperationalError, "readonly"):
                    store._db.execute("DELETE FROM pa_repo_active")

        after = self.db_path.stat()
        self.assertEqual(self.db_path.read_bytes(), original_bytes)
        self.assertEqual((after.st_size, after.st_mtime_ns),
                         (original_stat.st_size, original_stat.st_mtime_ns))

    def test_read_only_missing_database_is_not_created(self):
        missing_parent = self.root.parent / "missing-parent"
        missing_db = missing_parent / "index.sqlite"
        with self.assertRaises(sqlite3.OperationalError):
            with SQLiteRepositoryStore(missing_db, read_only=True):
                pass
        self.assertFalse(missing_parent.exists())
        self.assertFalse(missing_db.exists())

    def test_read_only_rejects_unrelated_database_without_schema_mutation(self):
        with closing(sqlite3.connect(self.db_path)) as db:
            db.execute("CREATE TABLE user_data(value TEXT)")
            db.execute("INSERT INTO user_data VALUES ('preserve')")
            db.commit()
        original_bytes = self.db_path.read_bytes()
        with self.assertRaisesRegex(sqlite3.DatabaseError, "missing required table"):
            with SQLiteRepositoryStore(self.db_path, read_only=True):
                pass
        self.assertEqual(self.db_path.read_bytes(), original_bytes)
        with closing(sqlite3.connect(self.db_path)) as db:
            names = {row[0] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'")}
            self.assertEqual(db.execute("SELECT value FROM user_data").fetchone()[0], "preserve")
        self.assertEqual(names, {"user_data"})

    def test_incompatible_reserved_schema_is_rejected_without_partial_tables(self):
        with closing(sqlite3.connect(self.db_path)) as db:
            db.execute("CREATE TABLE pa_repo_files(user_value TEXT)")
            db.commit()
        with self.assertRaisesRegex(sqlite3.DatabaseError, "incompatible repository store table"):
            with SQLiteRepositoryStore(self.db_path):
                pass
        with closing(sqlite3.connect(self.db_path)) as db:
            names = {row[0] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'")}
        self.assertEqual(names, {"pa_repo_files"})

    def test_reserved_tables_without_expected_primary_keys_are_rejected(self):
        with closing(sqlite3.connect(self.db_path)) as db:
            db.execute("CREATE TABLE pa_repo_active(root TEXT, generation TEXT)")
            db.commit()
        with self.assertRaisesRegex(sqlite3.DatabaseError, "incompatible repository store key"):
            with SQLiteRepositoryStore(self.db_path):
                pass
        with closing(sqlite3.connect(self.db_path)) as db:
            names = {row[0] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'")}
        self.assertEqual(names, {"pa_repo_active"})

    def test_cli_rejects_integer_outside_sqlite_range_without_traceback(self):
        self.write("a.py", "value = 1\n")
        result = subprocess.run(
            [sys.executable, "-m", "play_anything.cli", "index-repository",
             str(self.root), "--database", str(self.db_path), "--max-files", str(1 << 63)],
            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("max-files", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_query_cli_does_not_create_missing_database(self):
        result = subprocess.run(
            [sys.executable, "-m", "play_anything.cli", "query-repository",
             str(self.root), "--database", str(self.db_path)],
            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("no repository index", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse(self.db_path.exists())

    def test_python_module_cli_results_match_store_queries(self):
        self.write("a.py", "import b\n")
        self.write("b.py", "value = 1\n")
        cli = [sys.executable, "-m", "play_anything.cli"]
        common = [str(self.root), "--database", str(self.db_path)]
        index = subprocess.run(cli + ["index-repository", *common, "--all-files"],
                               cwd=Path(__file__).resolve().parents[1],
                               capture_output=True, text=True, timeout=10)
        self.assertEqual(index.returncode, 0, index.stderr)
        self.assertEqual(json.loads(index.stdout)["result"]["file_count"], 2)
        query = subprocess.run(cli + ["query-repository", *common, "--view", "imports"],
                               cwd=Path(__file__).resolve().parents[1],
                               capture_output=True, text=True, timeout=10)
        self.assertEqual(query.returncode, 0, query.stderr)
        cli_result = json.loads(query.stdout)
        with SQLiteRepositoryStore(self.db_path) as store:
            expected = store.imports(self.root)
        self.assertEqual(cli_result["result"], expected)

    def test_benchmark_store_command_reports_measured_store_counts(self):
        result = subprocess.run(
            [sys.executable, "scripts/benchmark_repository_ingestion.py", "--files", "4",
             "--functions-per-file", "1", "--mode", "store", "--repeats", "1"],
            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["mode"], "store")
        measurement = report["measurements"][0]
        self.assertEqual((measurement["files"], measurement["edges"]), (4, 4))
        self.assertEqual(measurement["cache_state"], "not_applicable")
        self.assertGreater(measurement["python_peak_bytes"], 0)

    def test_writer_timeout_preserves_the_previous_active_index(self):
        self.write("old.py", "value = 1\n")
        with SQLiteRepositoryStore(self.db_path) as store:
            old_status = store.rebuild(self.root)
            real_connect = sqlite3.connect
            with patch("play_anything.adapters.repository_store.sqlite3.connect",
                       side_effect=lambda *args, **kwargs: real_connect(
                           *args, **{**kwargs, "timeout": 0.02})):
                contender = SQLiteRepositoryStore(self.db_path)
                contender.__enter__()
            lock = real_connect(self.db_path, timeout=0.02)
            try:
                lock.execute("BEGIN IMMEDIATE")
                self.write("new.py", "value = 2\n")
                with self.assertRaises(sqlite3.OperationalError):
                    contender.rebuild(self.root)
            finally:
                lock.rollback()
                lock.close()
                contender.close()
            self.assertEqual(store.status(self.root)["generation"], old_status["generation"])
            self.assertEqual([row["path"] for row in store.files(self.root, limit=10)], ["old.py"])

    def test_page_read_keeps_one_generation_snapshot_during_concurrent_rebuild(self):
        self.write("old.py", "value = 1\n")
        with SQLiteRepositoryStore(self.db_path) as store:
            store.rebuild(self.root)
        self.write("new.py", "value = 2\n")

        writer_initialized = threading.Event()
        begin_rebuild = threading.Event()
        reader_captured_generation = threading.Event()
        writer_commit_attempt = threading.Event()
        reader_ident = []
        writer_ident = []
        page = []
        failures = []
        original_active = SQLiteRepositoryStore._active_generation

        def pause_reader_after_generation(db, root):
            generation = original_active(db, root)
            if threading.get_ident() == reader_ident[0]:
                reader_captured_generation.set()
                if not writer_commit_attempt.wait(3):
                    raise AssertionError("writer did not reach a commit attempt")
            return generation

        real_connect = sqlite3.connect

        class CommitTrackingConnection(sqlite3.Connection):
            def commit(self):
                if (writer_ident and threading.get_ident() == writer_ident[0] and
                        begin_rebuild.is_set()):
                    writer_commit_attempt.set()
                return super().commit()

        def connect_with_commit_tracking(*args, **kwargs):
            kwargs["factory"] = CommitTrackingConnection
            return real_connect(*args, **kwargs)

        def reader():
            reader_ident.append(threading.get_ident())
            try:
                with SQLiteRepositoryStore(self.db_path) as store:
                    page.extend(row["path"] for row in store.files(self.root, limit=10))
            except BaseException as error:
                failures.append(error)

        def writer():
            writer_ident.append(threading.get_ident())
            try:
                with SQLiteRepositoryStore(self.db_path) as store:
                    writer_initialized.set()
                    if not begin_rebuild.wait(3):
                        raise AssertionError("reader did not capture the active generation")
                    store.rebuild(self.root)
            except BaseException as error:
                failures.append(error)

        with patch.object(SQLiteRepositoryStore, "_active_generation",
                          staticmethod(pause_reader_after_generation)), patch(
                              "play_anything.adapters.repository_store.sqlite3.connect",
                              side_effect=connect_with_commit_tracking):
            writer_thread = threading.Thread(target=writer)
            writer_thread.start()
            self.assertTrue(writer_initialized.wait(3))
            reader_thread = threading.Thread(target=reader)
            reader_thread.start()
            self.assertTrue(reader_captured_generation.wait(3))
            begin_rebuild.set()
            reader_thread.join(3)
            writer_thread.join(3)

        self.assertFalse(reader_thread.is_alive())
        self.assertFalse(writer_thread.is_alive())
        self.assertEqual(failures, [])
        self.assertEqual(page, ["old.py"])
        with SQLiteRepositoryStore(self.db_path) as store:
            self.assertEqual([row["path"] for row in store.files(self.root, limit=10)],
                             ["new.py", "old.py"])

    def test_store_releases_each_summary_instead_of_retaining_repository_list(self):
        class Summary(dict):
            pass

        references = []

        def summaries(*args, **kwargs):
            for index in range(130):
                summary = Summary(path=f"module_{index:03}.py", lines_of_code=1,
                                  complexity=1.0, imports=[], analysis="python_ast")
                references.append(weakref.ref(summary))
                yield summary

        original_write_rows = SQLiteRepositoryStore._write_rows

        def inspect_batch(db, files, modules):
            gc.collect()
            self.assertLessEqual(sum(reference() is not None for reference in references), 1)
            return original_write_rows(db, files, modules)

        with SQLiteRepositoryStore(self.db_path) as store:
            with patch("play_anything.adapters.repository_store.iter_repository_summaries",
                       side_effect=summaries), patch.object(
                           SQLiteRepositoryStore, "_write_rows", side_effect=inspect_batch):
                status = store.rebuild(self.root, max_files=None)
        self.assertEqual(status["file_count"], 130)
        self.assertTrue(all(reference() is None for reference in references))


if __name__ == "__main__":
    unittest.main()
