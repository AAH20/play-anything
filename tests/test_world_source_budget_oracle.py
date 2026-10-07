"""Cross-mode checks for the source summaries represented in generated worlds."""
from pathlib import Path
import tempfile
import unittest

from play_anything.adapters.repo_rpg_generator import RepoRPGGenerator


class WorldSourceBudgetOracleTests(unittest.TestCase):
    def make_repo(self, files):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name) / "repo"
        root.mkdir()
        for name, source in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(source)
        return root

    @staticmethod
    def edge_pairs(world):
        names = {node.node_id: node.name for node in world.nodes}
        return {(names[edge.source], names[edge.target]) for edge in world.edges}

    def test_zero_and_exact_budget_preserve_only_observed_import_edges(self):
        source_a = b"import b\n"
        source_b = b"value = 1\n"
        root = self.make_repo({"a.py": source_a, "b.py": source_b})

        empty_read = RepoRPGGenerator.scan_local_directory(
            str(root), max_files=None, max_total_source_bytes=0)
        exact = RepoRPGGenerator.scan_local_directory(
            str(root), max_files=None,
            max_total_source_bytes=len(source_a) + len(source_b))

        self.assertEqual({node.name for node in empty_read.nodes}, {"a.py", "b.py"})
        self.assertEqual(self.edge_pairs(empty_read), set())
        self.assertEqual(empty_read.analysis["analysis_counts"], {
            "source_budget_exceeded": 2,
        })
        self.assertEqual(self.edge_pairs(exact), {("b.py", "a.py")})
        self.assertEqual(exact.analysis["analysis_counts"], {"python_ast": 2})
        self.assertEqual(exact.analysis["source_bytes_read"], len(source_a) + len(source_b))

    def test_oversized_first_file_does_not_block_later_import_resolution(self):
        source_a = b"import b\n"
        source_b = b"value = 1\n"
        root = self.make_repo({
            "00_large.py": b"#" * 64,
            "a.py": source_a,
            "b.py": source_b,
        })
        world = RepoRPGGenerator.scan_local_directory(
            str(root), max_files=None, max_file_bytes=16,
            max_total_source_bytes=len(source_a) + len(source_b))

        self.assertEqual([node.name for node in world.nodes], ["00_large.py", "a.py", "b.py"])
        self.assertEqual(self.edge_pairs(world), {("b.py", "a.py")})
        self.assertEqual(world.analysis["analysis_counts"], {
            "source_too_large": 1, "python_ast": 2,
        })
        self.assertEqual(world.analysis["source_bytes_read"], len(source_a) + len(source_b))

    def test_syntax_error_remains_a_file_node_without_invented_outgoing_imports(self):
        root = self.make_repo({"a.py": b"import b\n", "b.py": b"def broken(:\n"})
        world = RepoRPGGenerator.scan_local_directory(
            str(root), max_files=None, max_total_source_bytes=100)

        self.assertEqual(self.edge_pairs(world), {("b.py", "a.py")})
        self.assertEqual(world.analysis["analysis_counts"], {
            "python_ast": 1, "python_parse_error": 1,
        })
        self.assertEqual(world.analysis["status"], "partial")

    def test_warm_cache_and_cold_scan_produce_identical_world_projection(self):
        source_worker = b"def run():\n    return 1\n"
        root = self.make_repo({
            "consumer.py": b"import worker\n",
            "worker.py": source_worker,
        })
        with tempfile.TemporaryDirectory() as cache_dir:
            cache = Path(cache_dir) / "summaries.sqlite"
            cold = RepoRPGGenerator.scan_local_directory(
                str(root), max_files=None, cache_path=str(cache),
                max_total_source_bytes=1000)
            warm = RepoRPGGenerator.scan_local_directory(
                str(root), max_files=None, cache_path=str(cache),
                max_total_source_bytes=1000)

        self.assertEqual([node.name for node in cold.nodes], [node.name for node in warm.nodes])
        self.assertEqual([node.lines_of_code for node in cold.nodes],
                         [node.lines_of_code for node in warm.nodes])
        self.assertEqual(self.edge_pairs(cold), {("worker.py", "consumer.py")})
        self.assertEqual(self.edge_pairs(cold), self.edge_pairs(warm))
        self.assertEqual(cold.analysis, warm.analysis)

    def test_file_limit_lookahead_does_not_add_an_unmaterialized_import_target(self):
        source_a = b"import b\n"
        source_b = b"value = 1\n"
        root = self.make_repo({"a.py": source_a, "b.py": source_b})
        world = RepoRPGGenerator.scan_local_directory(
            str(root), max_files=1,
            max_total_source_bytes=len(source_a) + len(source_b))

        self.assertEqual([node.name for node in world.nodes], ["a.py"])
        self.assertEqual(self.edge_pairs(world), set())
        self.assertEqual(world.analysis["analysis_counts"], {"python_ast": 1})
        self.assertTrue(world.analysis["file_limit_reached"])
        self.assertEqual(world.analysis["source_bytes_read"], len(source_a) + len(source_b))


if __name__ == "__main__":
    unittest.main()
