"""Creator repository analysis provenance and completeness contracts."""

import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from play_anything.creator_server import (
    CREATOR_MAX_TOTAL_SOURCE_BYTES, CreatorState, git_clone, inspect_repository,
)


class CreatorAnalysisProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_empty_repository_is_reported_as_empty_without_fallback(self):
        report = inspect_repository(self.root, "fixture")
        analysis = report["analysis"]
        self.assertEqual(analysis["status"], "empty")
        self.assertFalse(analysis["complete"])
        self.assertFalse(analysis["sample_fallback"])
        self.assertEqual(analysis["file_count"], 0)
        self.assertIs(type(analysis["status"]), str)
        self.assertIs(type(analysis["complete"]), bool)
        self.assertIs(type(analysis["sample_fallback"]), bool)
        self.assertIs(type(analysis["file_count"]), int)
        self.assertIs(type(analysis["warnings"]), list)
        self.assertIs(report["graph"]["analysis"], analysis)
        self.assertNotIn(str(self.root), json.dumps(report))

    def test_graph_excludes_hidden_private_paths(self):
        private = self.root / ".aws"
        private.mkdir()
        (private / "credentials").write_text("token = 'private'\n", encoding="utf-8")
        (self.root / ".env").write_text("SECRET=value\n", encoding="utf-8")
        (self.root / "visible.py").write_text("value = 1\n", encoding="utf-8")
        report = inspect_repository(self.root, "fixture")
        graph_paths = [node.get("path", "") for node in report["graph"]["nodes"]]
        self.assertTrue(any(path == "visible.py" for path in graph_paths))
        self.assertFalse(any(
            path not in ("", ".") and (path.startswith(".") or "/." in path)
            for path in graph_paths
        ))
        self.assertNotIn("credentials", json.dumps(report))
        self.assertNotIn("SECRET=value", json.dumps(report))

    def test_generated_site_dist_is_not_reported_as_repository_source(self):
        generated = self.root / "site-dist"
        generated.mkdir()
        (generated / "bundle.js").write_text("export const generated = true;\n", encoding="utf-8")
        (self.root / "app.py").write_text("value = 1\n", encoding="utf-8")

        report = inspect_repository(self.root, "fixture")

        paths = [item["path"] for item in report["files"]]
        self.assertEqual(paths, ["app.py"])
        graph_paths = [node.get("path", "") for node in report["graph"]["nodes"]]
        self.assertFalse(any(path.startswith("site-dist/") for path in graph_paths))
        self.assertNotIn("bundle.js", json.dumps(report))

    def test_root_level_src_named_module_does_not_crash_graph_analysis(self):
        (self.root / "src.py").write_text("value = 1\n", encoding="utf-8")

        report = inspect_repository(self.root, "fixture")

        self.assertEqual(report["files"][0]["path"], "src.py")
        self.assertTrue(any(node.get("path") == "src.py" for node in report["graph"]["nodes"]))

    def test_graph_without_analysis_is_labeled_as_bundled_sample(self):
        state = CreatorState(self.root / "workspaces")
        sample_graph = {"analysis": {"status": "partial", "complete": False}}
        with patch("play_anything.creator_server.build_repository_graph", return_value=sample_graph):
            result = state.dispatch("/api/graph", {})
        self.assertEqual(result["analysis"]["status"], "sample_repo")
        self.assertTrue(result["analysis"]["sample_fallback"])
        self.assertEqual(result["analysis"]["source_kind"], "bundled_sample")

    def test_graph_rejects_unknown_analysis_id_instead_of_falling_back(self):
        state = CreatorState(self.root / "workspaces")
        with self.assertRaisesRegex(ValueError, "Analyze a repository first"):
            state.dispatch("/api/graph", {"analysis_id": "unknown"})

    def test_sample_analysis_is_labeled_as_bundled_sample(self):
        state = CreatorState(self.root / "workspaces")
        with patch("play_anything.creator_server.inspect_repository") as inspect:
            inspect.return_value = {"analysis": {"status": "sample_repo"}}
            result = state.dispatch("/api/analyze", {"sample": True})
        self.assertTrue(inspect.call_args.kwargs["sample_fallback"])
        self.assertEqual(
            inspect.call_args.kwargs["max_total_source_bytes"],
            CREATOR_MAX_TOTAL_SOURCE_BYTES,
        )
        self.assertEqual(result["analysis"]["status"], "sample_repo")

    def test_aggregate_source_budget_is_visible_for_summary_and_graph(self):
        (self.root / "a.py").write_text("value = 1\n")

        report = inspect_repository(
            self.root, "fixture", max_total_source_bytes=1,
        )

        analysis = report["analysis"]
        self.assertEqual(analysis["status"], "partial")
        self.assertFalse(analysis["complete"])
        self.assertEqual(analysis["source_budget_bytes"], 1)
        self.assertEqual(analysis["source_budget_exceeded_files"], 1)
        self.assertEqual(analysis["graph_source_budget_bytes"], 1)
        self.assertEqual(analysis["graph_source_budget_exceeded_files"], 1)
        self.assertEqual(analysis["source_bytes_read"], 0)
        self.assertEqual(analysis["graph_source_bytes_read"], 0)

    def test_workspace_creation_errors_do_not_expose_absolute_paths(self):
        state = CreatorState(self.root / "workspaces")
        private_path = str(state.root)
        state.analyses["fixture"] = {
            "path": self.root,
            "report": {"url": "fixture", "groups": []},
            "completed": True,
        }
        with patch(
            "play_anything.creator_server.tempfile.mkdtemp",
            side_effect=PermissionError(f"permission denied: {private_path}"),
        ), self.assertRaises(ValueError) as analyze_error:
            state.dispatch("/api/analyze", {"url": "https://github.com/team/project"})
        self.assertNotIn(private_path, str(analyze_error.exception))

        with patch(
            "play_anything.creator_server.tempfile.mkdtemp",
            side_effect=PermissionError(f"permission denied: {private_path}"),
        ), self.assertRaises(ValueError) as create_error:
            state.dispatch("/api/create", {"analysis_id": "fixture", "rights_reviewed": True})
        self.assertNotIn(private_path, str(create_error.exception))

    def test_clone_errors_do_not_expose_absolute_workspace_paths(self):
        private_path = str(self.root / "workspace-private")
        failed = SimpleNamespace(returncode=128, stderr=f"fatal: unable to write {private_path}")
        with patch("play_anything.creator_server.shutil.which", return_value="/usr/bin/git"), patch(
            "play_anything.creator_server.subprocess.run", return_value=failed
        ), self.assertRaises(ValueError) as raised:
            git_clone("https://github.com/team/project", self.root / "clone")
        self.assertIn("clone failed", str(raised.exception).lower())
        self.assertNotIn(private_path, str(raised.exception))

    def test_inventory_errors_do_not_expose_absolute_workspace_paths(self):
        private_path = str(self.root / "workspace-private")
        with patch(
            "play_anything.creator_server.iter_repository_summaries",
            side_effect=PermissionError(f"permission denied: {private_path}"),
        ), self.assertRaises(ValueError) as raised:
            inspect_repository(self.root, "fixture")
        self.assertNotIn(private_path, str(raised.exception))
        self.assertIn("permissionerror", str(raised.exception).lower())

    def test_failed_repository_inspection_removes_created_clone_container(self):
        state = CreatorState(self.root / "workspaces")
        with patch("play_anything.creator_server.git_clone"), patch(
            "play_anything.creator_server.inspect_repository",
            side_effect=OSError("fixture inventory failure"),
        ), self.assertRaises(OSError):
            state.dispatch(
                "/api/analyze", {"url": "https://github.com/team/project"}
            )
        self.assertEqual(list(state.root.iterdir()), [])

    def test_report_counts_parse_failures_unparsed_files_and_limits(self):
        (self.root / "bad.py").write_text("def broken(:\n", encoding="utf-8")
        (self.root / "module.go").write_text("package main\n", encoding="utf-8")
        (self.root / "huge.py").write_bytes(b"x" * 32)
        report = inspect_repository(
            self.root, "fixture", max_files=3, max_file_bytes=16
        )
        analysis = report["analysis"]
        self.assertEqual(analysis["parse_errors"], 1)
        self.assertEqual(analysis["unparsed_files"], 1)
        self.assertEqual(analysis["too_large_files"], 1)
        self.assertFalse(analysis["complete"])
        self.assertEqual(analysis["max_file_bytes"], 16)
        self.assertEqual(analysis["graph_max_file_bytes"], 16)
        self.assertEqual(report["graph"]["analysis"]["max_file_bytes"], 16)

    def test_file_limit_and_unreadable_file_are_visible(self):
        (self.root / "exact.py").write_text("x = 0\n", encoding="utf-8")
        exact = inspect_repository(self.root, "fixture", max_files=1)
        self.assertFalse(exact["analysis"]["file_limit_reached"])

        (self.root / "exact.py").unlink()
        (self.root / "a.py").write_text("x = 1\n", encoding="utf-8")
        (self.root / "b.py").write_text("x = 2\n", encoding="utf-8")
        report = inspect_repository(self.root, "fixture", max_files=1)
        self.assertTrue(report["analysis"]["file_limit_reached"])
        self.assertEqual(report["analysis"]["file_count"], 1)
        self.assertEqual(report["analysis"]["status"], "partial")
        self.assertTrue(report["truncated"])
        self.assertEqual(report["analysis"]["file_limit"], 1)

        path = self.root / "blocked.py"
        path.write_text("x = 3\n", encoding="utf-8")
        original_open = os.open

        def deny_one_file(candidate, *args, **kwargs):
            if Path(candidate).name == "blocked.py":
                raise PermissionError("fixture read denied")
            return original_open(candidate, *args, **kwargs)

        with patch("play_anything.adapters.repository_index.os.open", side_effect=deny_one_file):
            report = inspect_repository(self.root, "fixture", max_files=10)
        self.assertEqual(report["analysis"]["unreadable_files"], 1)
        self.assertFalse(report["analysis"]["complete"])
        self.assertEqual(report["analysis"]["status"], "partial")
        self.assertIn("unreadable", report["analysis"]["message"].lower())


if __name__ == "__main__":
    unittest.main()
