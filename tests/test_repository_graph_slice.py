import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from play_anything.adapters.repository_store import SQLiteRepositoryStore


class RepositoryGraphPageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.root = base / "repo"
        self.root.mkdir()
        self.store_path = base / "index.sqlite3"

    def write(self, relative, source="value = 1\n"):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")

    def test_pages_include_only_internal_edges_and_report_cross_page_coverage(self):
        self.write("a.py", "import b\nimport c\n")
        self.write("b.py")
        self.write("c.py")
        self.write("d.py")
        with SQLiteRepositoryStore(self.store_path) as store:
            store.rebuild(self.root, max_files=None)
            first = store.graph_page(self.root, limit=2, offset=0)
            second = store.graph_page(self.root, limit=2, offset=2)

        self.assertEqual([node["id"] for node in first["nodes"]], ["file:a.py", "file:b.py"])
        self.assertEqual(first["edges"], [{
            "source": "file:a.py", "target": "file:b.py", "relation": "imports",
            "confidence": "parsed",
        }])
        self.assertEqual(first["coverage"]["total_nodes"], 4)
        self.assertEqual(first["coverage"]["matching_nodes"], 4)
        self.assertEqual(first["coverage"]["omitted_cross_page_edges"], 1)
        self.assertEqual(first["coverage"]["omitted_page_edges"], 0)
        self.assertEqual(first["coverage"]["total_import_edges"], 2)
        self.assertTrue(first["coverage"]["has_next"])
        self.assertTrue(first["truncated"])
        self.assertEqual([node["id"] for node in second["nodes"]], ["file:c.py", "file:d.py"])
        self.assertEqual(second["coverage"]["omitted_cross_page_edges"], 1)
        self.assertFalse(second["coverage"]["has_next"])
        self.assertEqual(first["name"], "repo")
        self.assertNotIn(str(self.root), repr(first))
        self.assertEqual(first["analysis"]["source_kind"], "sqlite_file_import_page")

    def test_edge_cap_reports_omitted_internal_edges_without_phantom_nodes(self):
        dependencies = [f"m{index:02d}" for index in range(24)]
        self.write("a.py", "".join(f"import {name}\n" for name in dependencies))
        for name in dependencies:
            self.write(name + ".py")
        with SQLiteRepositoryStore(self.store_path) as store:
            store.rebuild(self.root, max_files=None)
            page = store.graph_page(self.root, limit=25, max_edges=3)

        self.assertEqual(len(page["nodes"]), 25)
        self.assertEqual(len(page["edges"]), 3)
        self.assertEqual(page["coverage"]["returned_page_edges"], 3)
        self.assertEqual(page["coverage"]["omitted_page_edges"], 21)
        self.assertEqual(page["coverage"]["omitted_cross_page_edges"], 0)
        self.assertTrue(page["truncated"])
        node_ids = {node["id"] for node in page["nodes"]}
        self.assertTrue(all(edge["source"] in node_ids and edge["target"] in node_ids
                            for edge in page["edges"]))

    def test_literal_search_has_distinct_matching_and_repository_totals(self):
        self.write("src/alpha.py")
        self.write("src/beta.py")
        self.write("docs/alpha.md")
        with SQLiteRepositoryStore(self.store_path) as store:
            store.rebuild(self.root, max_files=None)
            page = store.graph_page(self.root, limit=10, search="alpha")

        self.assertEqual([node["path"] for node in page["nodes"]], ["docs/alpha.md", "src/alpha.py"])
        self.assertEqual(page["coverage"]["total_nodes"], 3)
        self.assertEqual(page["coverage"]["matching_nodes"], 2)
        self.assertFalse(page["coverage"]["has_next"])
        self.assertTrue(page["coverage"]["filtered"])
        self.assertTrue(page["truncated"])

    def test_source_partial_and_scan_truncation_are_explicit(self):
        self.write("broken.py", "def invalid(:\n")
        self.write("notes.md")
        with SQLiteRepositoryStore(self.store_path) as store:
            store.rebuild(self.root, max_files=1, max_file_bytes=1)
            page = store.graph_page(self.root)

        self.assertEqual(page["coverage"]["status"], "partial")
        self.assertTrue(page["coverage"]["source_partial"])
        self.assertTrue(page["coverage"]["scan_truncated"])
        self.assertTrue(page["truncated"])
        self.assertEqual(page["analysis"]["status"], "partial")

    def test_page_and_edge_limits_are_exact_bounded_integers(self):
        self.write("a.py")
        with SQLiteRepositoryStore(self.store_path) as store:
            store.rebuild(self.root)
            for kwargs in ({"limit": True}, {"limit": 1001}, {"offset": -1},
                           {"max_edges": True}, {"max_edges": 10001}):
                with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                    store.graph_page(self.root, **kwargs)
            with self.assertRaises(TypeError):
                store.graph_page(self.root, search=3)

    def test_graph_export_offsets_fit_javascript_safe_integer_contract(self):
        self.write("a.py")
        with SQLiteRepositoryStore(self.store_path) as store:
            store.rebuild(self.root)
            last_safe_offset = (1 << 53) - 1
            page = store.graph_page(self.root, offset=last_safe_offset)
            self.assertEqual(page["coverage"]["offset"], last_safe_offset)
            self.assertEqual(page["coverage"]["returned_nodes"], 0)
            with self.assertRaisesRegex(ValueError, "JavaScript-safe integer"):
                store.graph_page(self.root, offset=1 << 53)

    def test_large_index_materializes_only_requested_summary_page(self):
        for index in range(160):
            self.write(f"src/file_{index:03d}.py")
        with SQLiteRepositoryStore(self.store_path) as store:
            store.rebuild(self.root, max_files=None)
            import json as json_module
            original_loads = json_module.loads
            with patch("play_anything.adapters.repository_store.json.loads",
                       wraps=original_loads) as loads:
                page = store.graph_page(self.root, limit=7, offset=80)

        self.assertEqual(len(page["nodes"]), 7)
        self.assertEqual(loads.call_count, 7)
        self.assertEqual(page["coverage"]["total_nodes"], 160)
        self.assertTrue(page["coverage"]["has_previous"])
        self.assertTrue(page["coverage"]["has_next"])


if __name__ == "__main__":
    unittest.main()
