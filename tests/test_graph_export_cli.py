import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

from play_anything.index_cli import run_index_command


class GraphExportCLI(unittest.TestCase):
    def invoke(self, command, arguments):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = run_index_command(command, arguments)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_large_budget_export_round_trips_exact_values_in_decimal_companions(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / 'repository'
            root.mkdir()
            (root / 'a.py').write_text('x = 1\n')
            common = [str(root), '--database', str(base / 'index.sqlite')]
            large_budget = sys.maxsize - 1
            code, _, errors = self.invoke('index-repository', common + [
                '--max-total-source-bytes', str(large_budget)])
            self.assertEqual(code, 0, errors)
            code, output, errors = self.invoke('query-repository', common + ['--view', 'graph'])
            self.assertEqual(code, 0, errors)
            graph = json.loads(output)
            self.assertIsNone(graph['analysis']['source_budget_bytes'])
            self.assertEqual(graph['analysis']['source_budget_bytes_exact'], str(large_budget))
            self.assertIsNone(graph['coverage']['source_budget_bytes'])
            self.assertEqual(graph['coverage']['source_budget_bytes_exact'], str(large_budget))
            self.assertEqual(graph['analysis']['source_bytes_read'], len('x = 1\n'))
            self.assertTrue(graph['analysis']['source_metrics_available'])

    def test_export_is_raw_importable_snapshot_with_honest_page_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'example'
            root.mkdir()
            for name, content in {'a.py': 'import b\n', 'b.py': 'import c\n', 'c.py': 'x = 1\n'}.items():
                (root / name).write_text(content)
            common = [str(root), '--database', str(Path(directory) / 'index.sqlite')]
            code, _, error = self.invoke('index-repository', common + ['--all-files'])
            self.assertEqual(code, 0, error)
            code, output, error = self.invoke('query-repository', common + ['--view', 'graph', '--limit', '2', '--edge-limit', '1'])
            self.assertEqual(code, 0, error)
            graph = json.loads(output)
            self.assertEqual(graph['version'], 1)
            self.assertEqual({node['id'] for node in graph['nodes']}, {'file:a.py', 'file:b.py'})
            self.assertEqual(len(graph['edges']), 1)
            self.assertTrue(graph['coverage']['has_next'])
            self.assertEqual(graph['coverage']['omitted_cross_page_edges'], 1)
            self.assertNotIn(str(root), output)
            self.assertNotIn('result', graph)
            code, output, error = self.invoke('query-repository', common + ['--view', 'graph', '--search', 'c.py'])
            self.assertEqual(code, 0, error)
            filtered = json.loads(output)
            self.assertEqual(filtered['coverage']['matching_nodes'], 1)
            self.assertEqual([node['path'] for node in filtered['nodes']], ['c.py'])
            self.assertEqual(filtered['edges'], [])
            code, output, error = self.invoke('query-repository', common + ['--view', 'status'])
            self.assertEqual(code, 0, error)
            self.assertEqual(json.loads(output)['schema_version'], 1)
            self.assertIn('result', json.loads(output))

    def test_invalid_graph_options_fail_before_database_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / 'must-not-exist.sqlite'
            common = [directory, '--database', str(database)]
            for extra in [['--edge-limit', '1'], ['--view', 'files', '--edge-limit', '1'],
                          ['--view', 'graph', '--edge-limit', '10001'],
                          ['--view', 'graph', '--path', 'a.py'],
                          ['--view', 'graph', '--direction', 'imports']]:
                with self.subTest(extra=extra):
                    code, output, error = self.invoke('query-repository', common + extra)
                    self.assertEqual(code, 2)
                    self.assertEqual(output, '')
                    self.assertIn('error:', error)
                    self.assertFalse(database.exists())
