"""Verify real CLI index/query results and failure exit statuses."""

import contextlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from play_anything.index_cli import run_index_command


class RepositoryIndexCLI(unittest.TestCase):
    def test_query_never_creates_database_or_modifies_invalid_database(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'repo'
            root.mkdir()
            database = Path(directory) / 'missing-parent' / 'index.sqlite'
            code, output, error = self.invoke('query-repository', [str(root), '--database', str(database)])
            self.assertEqual(code, 1)
            self.assertEqual(output, '')
            self.assertTrue(error)
            self.assertFalse(database.parent.exists())
            database = Path(directory) / 'unrelated.sqlite'
            original = b'not a SQLite repository index'
            database.write_bytes(original)
            code, output, error = self.invoke('query-repository', [str(root), '--database', str(database)])
            self.assertEqual(code, 1)
            self.assertEqual(output, '')
            self.assertTrue(error)
            self.assertEqual(database.read_bytes(), original)

    def test_out_of_range_page_and_irrelevant_direction_are_usage_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / 'must-not-be-created.sqlite'
            common = [directory, '--database', str(database)]
            cases = [
                ['--view', 'files', '--limit', '1001'],
                ['--view', 'files', '--offset', str(2**63)],
                ['--view', 'imports', '--direction', 'imported_by'],
                ['--direction', 'imports'],
            ]
            for extra in cases:
                with self.subTest(extra=extra):
                    code, output, error = self.invoke('query-repository', common + extra)
                    self.assertEqual(code, 2)
                    self.assertEqual(output, '')
                    self.assertIn('error:', error)
                    self.assertFalse(database.exists())
            for extra in [['--max-files', str(2**63)],
                          ['--max-file-bytes', str(2**63 - 1)]]:
                code, output, error = self.invoke('index-repository', common + extra)
                self.assertEqual(code, 2)
                self.assertEqual(output, '')
                self.assertFalse(database.exists())

    def invoke(self, command, arguments):
        out, error = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(error):
            code = run_index_command(command, arguments)
        return code, out.getvalue(), error.getvalue()

    def test_index_then_page_search_and_query_dependencies(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'repo'; root.mkdir()
            (root / 'a.py').write_text('import b\n')
            (root / 'b.py').write_text('def task(): return 1\n')
            common = [str(root), '--database', str(Path(directory) / 'index.sqlite')]
            code, output, error = self.invoke('index-repository', common + ['--all-files'])
            self.assertEqual(code, 0, error)
            self.assertEqual(json.loads(output)['result']['file_count'], 2)
            code, output, error = self.invoke('query-repository', common + ['--view', 'files', '--limit', '1', '--offset', '1'])
            self.assertEqual(code, 0, error); self.assertEqual(len(json.loads(output)['result']), 1)
            code, output, error = self.invoke('query-repository', common + ['--view', 'files', '--search', '%'])
            self.assertEqual(code, 0, error); self.assertEqual(json.loads(output)['result'], [])
            code, output, error = self.invoke('query-repository', common + ['--view', 'dependencies', '--path', 'a.py'])
            self.assertEqual(code, 0, error); self.assertEqual(len(json.loads(output)['result']), 1)

    def test_failed_input_has_no_result_on_stdout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'missing'
            common = [str(root), '--database', str(Path(directory) / 'index.sqlite')]
            code, output, error = self.invoke('index-repository', common)
            self.assertEqual(code, 1); self.assertEqual(output, ''); self.assertIn('error', error.lower())

    def test_corrupt_summary_rows_return_controlled_query_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'repo'; root.mkdir()
            (root / 'a.py').write_text('value = 1\n', encoding='utf-8')
            database = Path(directory) / 'index.sqlite'
            common = [str(root), '--database', str(database)]
            code, output, error = self.invoke('index-repository', common + ['--all-files'])
            self.assertEqual(code, 0, error)
            with sqlite3.connect(database) as db:
                before = db.execute('SELECT generation FROM pa_repo_active').fetchone()[0]
                db.execute("UPDATE pa_repo_files SET summary_json = '[]'")
                db.commit()

            for view in ('files', 'graph'):
                with self.subTest(view=view):
                    code, output, error = self.invoke(
                        'query-repository', common + ['--view', view])
                    self.assertEqual(code, 1)
                    self.assertEqual(output, '')
                    self.assertIn('Repository index error:', error)
                    self.assertNotIn('Traceback', error)

            with sqlite3.connect(database) as db:
                after = db.execute('SELECT generation FROM pa_repo_active').fetchone()[0]
            self.assertEqual(after, before)

    def test_invalid_usage_and_help_status(self):
        common = ['repo', '--database', 'index.sqlite']
        for extra in (['--limit', '0'], ['--offset', '-1'], ['--view', 'dependencies'], ['--search', 'x']):
            with self.subTest(extra=extra):
                code, output, _ = self.invoke('query-repository', common + extra)
                self.assertEqual(code, 2); self.assertEqual(output, '')
        code, output, _ = self.invoke('query-repository', ['--help'])
        self.assertEqual(code, 0); self.assertIn('--database', output)

    def test_database_inside_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            code, output, error = self.invoke('index-repository', [directory, '--database', str(Path(directory) / 'index.sqlite')])
            self.assertEqual(code, 1); self.assertEqual(output, ''); self.assertTrue(error)
