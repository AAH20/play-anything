"""Acceptance coverage for inventory-preserving aggregate source admission."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

from play_anything.index_cli import run_index_command


class IndexSourceBudgetCLI(unittest.TestCase):
    def invoke(self, command, arguments):
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            code = run_index_command(command, list(map(str, arguments)))
        return code, output.getvalue(), errors.getvalue()

    def test_budget_retains_inventory_and_reports_graph_omissions(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / 'repository'
            root.mkdir()
            source = 'import b\ndef first(): return 1\n'
            (root / 'a.py').write_text(source)
            (root / 'b.py').write_text('def second(): return 2\n')
            (root / 'empty.py').write_text('')
            args = [root, '--database', base / 'index.sqlite']
            code, output, errors = self.invoke('index-repository', args +
                                              ['--max-total-source-bytes', len(source.encode())])
            self.assertEqual(code, 0, errors)
            status = json.loads(output)['result']
            self.assertEqual(status['source_bytes_read'], len(source.encode()))
            self.assertEqual(status['source_budget_bytes'], len(source.encode()))
            self.assertEqual(status['source_budget_exceeded_files'], 1)
            self.assertTrue(status['source_budget_exhausted'])
            code, output, errors = self.invoke('query-repository', args + ['--view', 'graph'])
            self.assertEqual(code, 0, errors)
            graph = json.loads(output)
            self.assertEqual({node['path'] for node in graph['nodes']}, {'a.py', 'b.py', 'empty.py'})
            self.assertFalse(graph['coverage']['complete'])
            self.assertTrue(graph['coverage']['source_partial'])
            self.assertEqual(graph['analysis']['source_budget_exceeded_files'], 1)

    def test_zero_and_explicit_uncapped_modes_are_distinct(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / 'repository'
            root.mkdir()
            (root / 'a.py').write_text('def first(): return 1\n')
            args = [root, '--database', base / 'index.sqlite']
            code, output, errors = self.invoke('index-repository', args + ['--max-total-source-bytes', 0])
            self.assertEqual(code, 0, errors)
            status = json.loads(output)['result']
            self.assertEqual(status['source_bytes_read'], 0)
            self.assertEqual(status['source_budget_exceeded_files'], 1)
            code, output, errors = self.invoke('index-repository', args + ['--uncapped-total-source-bytes'])
            self.assertEqual(code, 0, errors)
            status = json.loads(output)['result']
            self.assertIsNone(status['source_budget_bytes'])
            self.assertEqual(status['source_budget_exceeded_files'], 0)
            self.assertFalse(status['source_budget_exhausted'])

    def test_invalid_budget_usage_does_not_create_a_database(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            database = base / 'must-not-exist.sqlite'
            args = [base, '--database', database]
            for extra in [['--max-total-source-bytes', -1],
                          ['--max-total-source-bytes', sys.maxsize],
                          ['--max-total-source-bytes', '1.5'],
                          ['--max-total-source-bytes', 0, '--uncapped-total-source-bytes']]:
                with self.subTest(extra=extra):
                    code, output, errors = self.invoke('index-repository', args + extra)
                    self.assertEqual(code, 2)
                    self.assertEqual(output, '')
                    self.assertIn('error:', errors)
                    self.assertFalse(database.exists())

    def test_large_valid_caps_export_without_javascript_precision_loss(self):
        if sys.maxsize <= 2 ** 53:
            self.skipTest('This platform cannot configure caps above JavaScript safe integers.')
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / 'repository'
            root.mkdir()
            source = 'def first(): return 1\n'
            (root / 'a.py').write_text(source)
            args = [root, '--database', base / 'index.sqlite']
            cap = sys.maxsize - 1
            code, output, errors = self.invoke('index-repository', args +
                ['--max-total-source-bytes', cap, '--max-file-bytes', cap, '--max-files', cap])
            self.assertEqual(code, 0, errors)
            # The Python status contract keeps the original exact integer.
            self.assertEqual(json.loads(output)['result']['source_budget_bytes'], cap)
            code, output, errors = self.invoke('query-repository', args + ['--view', 'graph'])
            self.assertEqual(code, 0, errors)
            graph = json.loads(output)
            for section, keys in [('analysis', ['source_budget_bytes', 'max_file_bytes', 'file_limit']),
                                  ('coverage', ['source_budget_bytes', 'max_total_source_bytes',
                                                'max_file_bytes', 'max_files'])]:
                for key in keys:
                    self.assertIsNone(graph[section][key])
                    self.assertEqual(graph[section][key + '_exact'], str(cap))
            self.assertEqual(graph['analysis']['source_bytes_read'], len(source.encode()))
            self.assertTrue(graph['coverage']['source_metrics_available'])


if __name__ == '__main__':
    unittest.main()
