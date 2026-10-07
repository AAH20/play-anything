"""Measure Creator source reads without changing exported summary contracts."""
from pathlib import Path
import tempfile
import unittest

from play_anything.creator_server import inspect_repository


class CreatorSourceAccountingTests(unittest.TestCase):
    def test_uncapped_scan_reports_actual_source_reads_and_preserves_summary_shape(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = b'value = 1\n'
            (root / 'sample.py').write_bytes(source)
            report = inspect_repository(root, 'fixture')
        analysis = report['analysis']
        self.assertEqual(analysis['source_bytes_read'], len(source))
        self.assertEqual(analysis['graph_source_bytes_read'], len(source))
        self.assertIsNone(analysis['source_budget_bytes'])
        self.assertFalse(analysis['source_budget_exhausted'])
        for summary in report['files']:
            self.assertFalse(set(summary) & {
                'source_bytes_read', 'source_budget_bytes',
                'source_budget_exhausted', 'source_budget_exceeded_files'})

    def test_lookahead_reads_are_charged_without_exporting_its_summary(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = b'value = 1\n'
            for name in ('a.py', 'b.py'):
                (root / name).write_bytes(source)
            report = inspect_repository(root, 'fixture', max_files=1)
        self.assertEqual(len(report['files']), 1)
        self.assertEqual(report['analysis']['source_bytes_read'], 2 * len(source))
        self.assertTrue(report['analysis']['file_limit_reached'])
        self.assertEqual(report['analysis']['status'], 'partial')

    def test_zero_and_exact_budgets_keep_actual_read_counts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = b'value = 1\n'
            (root / 'sample.py').write_bytes(source)
            zero = inspect_repository(root, 'fixture', max_total_source_bytes=0)
            exact = inspect_repository(root, 'fixture', max_total_source_bytes=len(source))
        self.assertEqual(zero['analysis']['source_bytes_read'], 0)
        self.assertEqual(zero['analysis']['source_budget_exceeded_files'], 1)
        self.assertEqual(exact['analysis']['source_bytes_read'], len(source))
        self.assertEqual(exact['analysis']['source_budget_exceeded_files'], 0)
        self.assertTrue(exact['analysis']['source_budget_exhausted'])
        self.assertEqual(exact['files'][0]['source_bytes_read'], len(source))
        self.assertEqual(exact['files'][0]['source_budget_bytes'], len(source))
