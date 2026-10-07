import unittest
import tracemalloc
import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from scripts.benchmark_repository_ingestion import benchmark, main


class IngestionBenchmarkTests(unittest.TestCase):
    def test_output_write_failure_is_reported_without_success_json(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'missing-parent' / 'report.json'
            stdout, stderr = io.StringIO(), io.StringIO()
            arguments = ['benchmark', '--files', '1', '--functions-per-file', '1',
                         '--repeats', '1', '--output', str(output)]
            with patch.object(sys, 'argv', arguments), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                self.assertEqual(main(), 1)
            self.assertEqual(stdout.getvalue(), '')
            self.assertIn('Benchmark error:', stderr.getvalue())
            self.assertNotIn('Traceback', stderr.getvalue())

    def test_durable_store_records_all_ring_edges_without_building_world(self):
        report = benchmark(4, 1, mode='store', repeats=2)
        self.assertIn('main SQLite file st_size', report['sqlite_database_measurement'])
        for measurement in report['measurements']:
            self.assertEqual(measurement['files'], 4)
            self.assertEqual(measurement['edges'], 4)
            self.assertFalse(measurement['partial'])
            self.assertEqual(measurement['cache_state'], 'not_applicable')
            self.assertGreater(measurement['sqlite_database_bytes'], 0)

    def test_store_mode_does_not_claim_summary_cache_benefit(self):
        with self.assertRaisesRegex(ValueError, 'summary caching'):
            benchmark(2, 1, mode='store', cache=True)

    def test_graph_page_mode_separates_index_setup_from_repeated_page_queries(self):
        report = benchmark(6, 1, mode='graph-page', repeats=2,
                           page_limit=2, edge_limit=1, page_offset=0)
        self.assertEqual(report['mode'], 'graph-page')
        setup = report['setup_metrics']
        self.assertEqual(setup['indexed_files'], 6)
        self.assertEqual(setup['indexed_import_edges'], 6)
        self.assertGreater(setup['index_build_python_peak_bytes'], 0)
        self.assertGreater(setup['sqlite_database_bytes'], 0)
        self.assertEqual(len(report['measurements']), 2)
        for measurement in report['measurements']:
            self.assertEqual(measurement['returned_files'], 2)
            self.assertLessEqual(measurement['returned_page_edges'], 1)
            self.assertGreater(measurement['sqlite_statement_count'], 0)
            self.assertGreater(measurement['python_peak_bytes'], 0)
            self.assertIn('omitted_cross_page_edges', measurement)
            self.assertIn('query_elapsed_seconds', measurement)
        self.assertIn('query only', report['memory_measurement'])

    def test_aggregate_source_budget_reports_zero_small_exact_and_uncapped_modes(self):
        fixture = benchmark(1, 1, mode='index', repeats=1)
        per_file_bytes = fixture['fixture_source_bytes']
        total_bytes = per_file_bytes * 4
        for mode in ('index', 'store', 'graph-page'):
            with self.subTest(mode=mode):
                for budget, expected_bytes, expected_excluded in (
                        (0, 0, 4), (per_file_bytes, per_file_bytes, 3),
                        (total_bytes, total_bytes, 0), (None, total_bytes, 0)):
                    report = benchmark(4, 1, mode=mode, repeats=1,
                                       max_total_source_bytes=budget,
                                       page_limit=2 if mode == 'graph-page' else None)
                    metrics = (report['setup_metrics'] if mode == 'graph-page'
                               else report['measurements'][0])
                    self.assertEqual(report['max_total_source_bytes'], budget)
                    self.assertEqual(metrics['source_bytes_read'], expected_bytes)
                    self.assertEqual(metrics['source_budget_bytes'], budget)
                    self.assertEqual(metrics['source_budget_exceeded_files'], expected_excluded)
                    self.assertTrue(metrics['source_metrics_available'])
                    self.assertEqual(metrics['source_budget_exhausted'], budget is not None)
                    if mode == 'index':
                        parsed = report['measurements'][0]['analysis_counts'].get('python_ast', 0)
                        self.assertEqual(parsed, 4 - expected_excluded)
                    else:
                        self.assertEqual(metrics['indexed_files'] if mode == 'graph-page'
                                         else report['measurements'][0]['files'], 4)
                        self.assertEqual(metrics['index_partial'] if mode == 'graph-page'
                                         else report['measurements'][0]['partial'], expected_excluded > 0)
                        if mode == 'graph-page':
                            self.assertEqual(report['measurements'][0]['returned_files'], 2)
                            self.assertIn('query only', report['memory_measurement'])

    def test_aggregate_source_budget_rejects_invalid_values(self):
        for invalid in (True, False, -1, 1.5, sys.maxsize):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                benchmark(1, 1, mode='store', max_total_source_bytes=invalid)
        with self.assertRaises(ValueError):
            benchmark(1, 1, mode='world', max_total_source_bytes=True)

    def test_aggregate_source_budget_cli_accepts_zero_in_graph_and_world_modes(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        arguments = ['benchmark', '--files', '3', '--functions-per-file', '1',
                     '--mode', 'graph-page', '--repeats', '1', '--page-limit', '2',
                     '--max-total-source-bytes', '0']
        with patch.object(sys, 'argv', arguments), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            self.assertEqual(main(), 0)
        report = json.loads(stdout.getvalue())
        setup = report['setup_metrics']
        self.assertEqual(report['max_total_source_bytes'], 0)
        self.assertEqual(setup['source_budget_bytes'], 0)
        self.assertEqual(setup['source_bytes_read'], 0)
        self.assertEqual(setup['source_budget_exceeded_files'], 3)
        self.assertIn('not process RSS', report['memory_measurement'])

        stdout, stderr = io.StringIO(), io.StringIO()
        arguments = ['benchmark', '--files', '1', '--functions-per-file', '1',
                     '--mode', 'index', '--repeats', '1',
                     '--max-total-source-bytes', str(sys.maxsize - 1)]
        with patch.object(sys, 'argv', arguments), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            self.assertEqual(main(), 0)
        report = json.loads(stdout.getvalue())
        self.assertEqual(report['max_total_source_bytes'], sys.maxsize - 1)
        self.assertEqual(report['measurements'][0]['source_budget_bytes'], sys.maxsize - 1)
        self.assertGreater(report['measurements'][0]['source_bytes_read'], 0)

        stdout, stderr = io.StringIO(), io.StringIO()
        arguments = ['benchmark', '--files', '1', '--functions-per-file', '1',
                     '--mode', 'world', '--max-total-source-bytes', '0']
        with patch.object(sys, 'argv', arguments), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            self.assertEqual(main(), 0)
        report = json.loads(stdout.getvalue())
        measurement = report['measurements'][0]
        self.assertEqual(measurement['source_bytes_read'], 0)
        self.assertEqual(measurement['source_budget_exceeded_files'], 1)
        self.assertEqual(measurement['status'], 'partial')
        self.assertEqual(stderr.getvalue(), '')

    def test_graph_page_query_timer_excludes_fixture_and_index_timers(self):
        ticks = iter((0.0, 2.0, 10.0, 14.0, 20.0, 21.0))
        with patch('scripts.benchmark_repository_ingestion.time.perf_counter',
                   side_effect=lambda: next(ticks)):
            report = benchmark(2, 1, mode='graph-page', repeats=1,
                               page_limit=1, edge_limit=1)
        self.assertEqual(report['setup_metrics']['fixture_creation_seconds'], 2.0)
        self.assertEqual(report['setup_metrics']['index_build_seconds'], 4.0)
        self.assertEqual(report['measurements'][0]['query_elapsed_seconds'], 1.0)

    def test_graph_page_options_are_rejected_for_other_modes(self):
        for option in ({'page_limit': 2}, {'page_offset': 1},
                       {'edge_limit': 5}, {'search': 'module'}):
            with self.subTest(option=option), self.assertRaisesRegex(ValueError, 'only valid'):
                benchmark(2, 1, mode='index', repeats=1, **option)

    def test_graph_page_api_options_are_validated(self):
        for option in ({'page_limit': True}, {'page_limit': 1001},
                       {'page_offset': -1}, {'page_offset': True},
                       {'edge_limit': 0}, {'edge_limit': 10001}):
            with self.subTest(option=option), self.assertRaises(ValueError):
                benchmark(2, 1, mode='graph-page', repeats=1, **option)

    def test_graph_page_search_is_literal_and_reports_filtered_counts(self):
        report = benchmark(6, 1, mode='graph-page', repeats=1,
                           page_limit=5, search='module_00000')
        measurement = report['measurements'][0]
        self.assertEqual(measurement['matching_files'], 1)
        self.assertEqual(measurement['returned_files'], 1)
        self.assertEqual(measurement['total_files'], 6)

    def test_cli_emits_raw_graph_page_and_rejects_page_flags_for_index_mode(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        arguments = ['benchmark', '--files', '4', '--functions-per-file', '1',
                     '--mode', 'graph-page', '--page-limit', '2', '--edge-limit', '1',
                     '--page-offset', '1', '--repeats', '1']
        with patch.object(sys, 'argv', arguments), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            self.assertEqual(main(), 0)
        report = json.loads(stdout.getvalue())
        self.assertEqual(report['mode'], 'graph-page')
        self.assertEqual(report['page_limit'], 2)
        self.assertEqual(report['page_offset'], 1)
        self.assertIn('setup_metrics', report)
        self.assertNotIn('Benchmark error:', stderr.getvalue())

        arguments = ['benchmark', '--files', '2', '--mode', 'index', '--page-limit', '2']
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(sys, 'argv', arguments), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as error:
                main()
        self.assertEqual(error.exception.code, 2)
        self.assertEqual(stdout.getvalue(), '')
        self.assertIn('require --mode graph-page', stderr.getvalue())

    def test_existing_tracer_is_not_reset_or_stopped(self):
        tracemalloc.start()
        try:
            with self.assertRaisesRegex(RuntimeError, 'existing tracemalloc'):
                benchmark(2, 1)
            self.assertTrue(tracemalloc.is_tracing())
        finally:
            tracemalloc.stop()

    def test_index_fixture_has_measured_counts_and_cache_repeats(self):
        report = benchmark(4, 2, cache=True)
        self.assertEqual(report["workload"], "synthetic_python_module_ring")
        self.assertGreater(report["fixture_source_bytes"], 0)
        self.assertEqual([run["cache_state"] for run in report["measurements"]], ["cold", "warm"])
        for run in report["measurements"]:
            self.assertEqual(run["files"], 4)
            self.assertEqual(run["analysis_counts"], {"python_ast": 4})
            self.assertGreater(run["python_peak_bytes"], 0)
            self.assertGreaterEqual(run["elapsed_seconds"], 0)

    def test_world_fixture_resolves_module_ring(self):
        report = benchmark(4, 1, mode="world", repeats=1)
        self.assertEqual(report["measurements"][0]["nodes"], 4)
        self.assertEqual(report["measurements"][0]["edges"], 4)

    def test_small_source_cap_is_reported_instead_of_parsed(self):
        report = benchmark(2, 1, max_file_bytes=1, repeats=1)
        self.assertEqual(report["measurements"][0]["analysis_counts"], {"source_too_large": 2})

    def test_invalid_fixture_parameters_fail_before_measurement(self):
        for invalid in (0, -1, True, 1.5):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                benchmark(invalid, 1)

    def test_source_byte_cap_api_rejects_invalid_and_unreadable_sizes_before_fixture_creation(self):
        invalid_caps = (True, False, 0, -1, 1.5, sys.maxsize, sys.maxsize + 1)
        for mode in ('index', 'world', 'store'):
            for invalid in invalid_caps:
                with self.subTest(mode=mode, invalid=invalid), patch(
                        'scripts.benchmark_repository_ingestion.tempfile.TemporaryDirectory') as tempdir:
                    with self.assertRaisesRegex(ValueError, 'max_file_bytes'):
                        benchmark(1, 1, mode=mode, repeats=1, max_file_bytes=invalid)
                    tempdir.assert_not_called()
