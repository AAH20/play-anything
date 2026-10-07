"""Exercise the actual world-preview CLI with explicit source-read budgets."""
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from play_anything.cli import main
from scripts.benchmark_repository_ingestion import benchmark
from play_anything.index_cli import run_index_command


class WorldBudgetCLITests(unittest.TestCase):
    def invoke(self, arguments):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(sys, 'argv', ['play-anything', *arguments]), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main()
        return code, stdout.getvalue(), stderr.getvalue()

    def test_zero_budget_retains_file_inventory_and_announces_partial_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'module.py'
            source.write_text('def observed_function():\n    return 42\n')
            code, stdout, stderr = self.invoke([
                'play', temporary, '--max-total-source-bytes', '0'])
        self.assertEqual(code, 0, stderr)
        self.assertIn('Source coverage: partial', stdout)
        self.assertIn('0 bytes read of a 0-byte cap', stdout)
        self.assertIn('1 files excluded', stdout)
        self.assertIn('remains in RAM', stdout)
        self.assertNotIn('synthetic fallback entities', stdout)

    def test_exact_source_fill_is_complete_without_exclusions(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = b'def observed_function():\n    return 42\n'
            (Path(temporary) / 'module.py').write_bytes(source)
            code, stdout, stderr = self.invoke([
                'play', temporary, '--max-total-source-bytes', str(len(source))])
        self.assertEqual(code, 0, stderr)
        self.assertIn('Source coverage: complete', stdout)
        self.assertIn(f'{len(source)} bytes read', stdout)
        self.assertIn('0 files excluded', stdout)

    def test_invalid_options_do_not_start_world_generation(self):
        arguments = [
            ['play', '--max-total-source-bytes', '0'],
            ['play', '/nonexistent', '--max-total-source-bytes', '-1'],
            ['play', '/nonexistent', '--max-total-source-bytes', str(sys.maxsize)],
            ['play', '/nonexistent', '--max-total-source-bytes', '1.5'],
            ['play', '/nonexistent', '--unknown-option'],
            ['play', '/nonexistent', 'unexpected-extra-path'],
        ]
        for arguments_for_case in arguments:
            with self.subTest(arguments=arguments_for_case), \
                    patch('play_anything.cli.PlayAnythingEngine') as engine:
                code, stdout, stderr = self.invoke(arguments_for_case)
                self.assertEqual(code, 2)
                self.assertEqual(stdout, '')
                self.assertTrue(stderr)
                engine.assert_not_called()

    def test_empty_repository_labels_synthetic_fallback(self):
        with tempfile.TemporaryDirectory() as temporary:
            code, stdout, stderr = self.invoke([
                'play', temporary, '--max-total-source-bytes', '0'])
        self.assertEqual(code, 0, stderr)
        self.assertIn('Source coverage: empty', stdout)
        self.assertIn('synthetic fallback entities', stdout)
        self.assertIn('not observed repository code', stdout)

    def test_file_count_cap_and_lookahead_are_disclosed_separately_from_source_budget(self):
        with tempfile.TemporaryDirectory() as temporary:
            for number in range(51):
                (Path(temporary) / f'module_{number:02d}.py').write_text('value = 1\n')
            code, stdout, stderr = self.invoke([
                'play', temporary, '--max-total-source-bytes', '10000'])
        self.assertEqual(code, 0, stderr)
        self.assertIn('Source coverage: partial', stdout)
        self.assertIn('File inventory in this world: 50', stdout)
        self.assertIn('Configured file limit reached (50)', stdout)
        self.assertIn('bounded lookahead', stdout)
        self.assertIn('0 files excluded by the source-read budget', stdout)

    def test_benchmark_world_budget_retains_ring_inventory_without_fake_edges(self):
        report = benchmark(4, 1, mode='world', repeats=1, max_total_source_bytes=0)
        measurement = report['measurements'][0]
        self.assertEqual(measurement['file_count'], 4)
        self.assertEqual(measurement['nodes'], 4)
        self.assertEqual(measurement['edges'], 0)
        self.assertEqual(measurement['source_bytes_read'], 0)
        self.assertEqual(measurement['source_budget_exceeded_files'], 4)
        self.assertEqual(measurement['status'], 'partial')
        self.assertIn('not process RSS', report['memory_measurement'])

    def test_unsafe_graph_offset_is_rejected_before_fixture_creation(self):
        with patch('scripts.benchmark_repository_ingestion.tempfile.TemporaryDirectory') as directory:
            with self.assertRaisesRegex(ValueError, 'portable JSON'):
                benchmark(1, 1, mode='graph-page', page_offset=2**53)
            directory.assert_not_called()

    def test_graph_cli_rejects_unsafe_offset_before_opening_database(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / 'missing.sqlite'
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                code = run_index_command('query-repository', [
                    temporary, '--database', str(database), '--view', 'graph',
                    '--offset', str(2**53)])
            self.assertEqual(code, 2)
            self.assertIn('portable JSON/Graph Studio', stderr.getvalue())
            self.assertFalse(database.exists())
