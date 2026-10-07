from pathlib import Path
import sys
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from play_anything.core.repository_graph import build_repository_graph, _read_capped_source


class RepositoryGraphSourceLimits(unittest.TestCase):
    @unittest.skipUnless(hasattr(os, 'mkfifo') and hasattr(os, 'O_NONBLOCK'),
                         'Requires POSIX FIFO/nonblocking support')
    def test_fifo_source_is_rejected_without_blocking(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'source.py'
            os.mkfifo(path)
            code = ("from pathlib import Path; import sys; "
                    "from play_anything.core.repository_graph import _read_capped_source; "
                    "\ntry: _read_capped_source(Path(sys.argv[1]),1000)"
                    "\nexcept OSError: print('rejected')")
            result = subprocess.run([sys.executable, '-c', code, str(path)],
                                    capture_output=True, text=True, timeout=3)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), 'rejected')

    @unittest.skipUnless(hasattr(os, 'mkfifo') and hasattr(os, 'O_NONBLOCK'),
                         'Requires POSIX FIFO/nonblocking support')
    def test_source_replaced_by_fifo_after_inventory_is_reported_unreadable(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory).resolve() / 'race.py'
            source.write_text('def old_source(): pass\n')
            original_open = os.open

            def replace_before_open(path, flags, *args, **kwargs):
                if Path(path) == source:
                    source.unlink()
                    os.mkfifo(source)
                return original_open(path, flags, *args, **kwargs)

            with patch('play_anything.core.repository_graph.os.open', replace_before_open):
                graph = build_repository_graph(directory)
            self.assertEqual(graph['summary']['files'], 1)
            self.assertEqual(graph['analysis']['unreadable_files'], 1)
            self.assertEqual(graph['analysis']['source_bytes_read'], 0)
            self.assertFalse(graph['analysis']['complete'])

    @unittest.skipUnless(hasattr(os, 'O_NOFOLLOW'), 'Requires no-follow open support')
    def test_source_replaced_by_symlink_never_reads_external_source(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            source = Path(directory).resolve() / 'race.py'
            source.write_text('def old_source(): pass\n')
            external = Path(outside) / 'external.py'
            external.write_text('def private_external_symbol(): pass\n')
            original_open = os.open

            def replace_before_open(path, flags, *args, **kwargs):
                if Path(path) == source:
                    source.unlink()
                    source.symlink_to(external)
                return original_open(path, flags, *args, **kwargs)

            with patch('play_anything.core.repository_graph.os.open', replace_before_open):
                graph = build_repository_graph(directory)
            self.assertEqual(graph['analysis']['unreadable_files'], 1)
            self.assertEqual(graph['analysis']['source_bytes_read'], 0)
            self.assertFalse(any(n.get('name') == 'private_external_symbol'
                                 for n in graph['nodes']))

    def test_repeated_qualified_names_cannot_bypass_symbol_limit(self):
        fixtures = [
            'def same(): pass\n' * 30,
            'class Same: pass\n' * 30,
            'class Owner:\n' + '    def same(self): pass\n' * 30,
        ]
        for source in fixtures:
            with self.subTest(source=source[:30]), tempfile.TemporaryDirectory() as directory:
                (Path(directory) / 'repeated.py').write_text(source)
                graph = build_repository_graph(directory, max_symbols=2)
                symbols = [n for n in graph['nodes'] if n['kind'] in ('class', 'function')]
                self.assertEqual(len(symbols), 2)
                self.assertTrue(graph['analysis']['symbol_limit_reached'])
                self.assertFalse(graph['analysis']['complete'])
                identifiers = {n['id'] for n in graph['nodes']}
                self.assertTrue(all(e['source'] in identifiers and e['target'] in identifiers
                                    for e in graph['edges']))

    def test_total_budget_keeps_inventory_and_stops_source_analysis(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in ['a.py', 'b.py']:
                (Path(directory) / name).write_bytes(b'x = 1\n')
            graph = build_repository_graph(directory, max_total_source_bytes=6)
            self.assertEqual(graph['summary']['files'], 2)
            self.assertEqual(graph['analysis']['analyzed_files'], 1)
            self.assertEqual(graph['analysis']['source_budget_exceeded_files'], 1)
            self.assertEqual(graph['analysis']['source_bytes_read'], 6)
            self.assertEqual(graph['analysis']['source_budget_bytes'], 6)
            self.assertFalse(graph['analysis']['complete'])
            zero = build_repository_graph(directory, max_total_source_bytes=0)
            self.assertEqual(zero['summary']['files'], 2)
            self.assertEqual(zero['analysis']['source_bytes_read'], 0)
            self.assertEqual(zero['analysis']['source_budget_exceeded_files'], 2)
            uncapped = build_repository_graph(directory)
            self.assertEqual(uncapped['analysis']['source_bytes_read'], 12)
            self.assertEqual(uncapped['analysis']['source_budget_exceeded_files'], 0)
            exact = build_repository_graph(directory, max_total_source_bytes=12)
            self.assertTrue(exact['analysis']['source_budget_exhausted'])
            self.assertEqual(exact['analysis']['source_budget_exceeded_files'], 0)

    def test_total_budget_types_are_validated_before_io(self):
        for budget in [True, False, -1, 1.5, sys.maxsize]:
            with self.subTest(budget=budget), patch('play_anything.core.repository_graph.Path.resolve', side_effect=AssertionError('filesystem access')):
                with self.assertRaises(ValueError):
                    build_repository_graph('missing', max_total_source_bytes=budget)

    def test_growing_source_charges_one_sentinel_then_stops_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'a.py').write_bytes(b'a')
            (root / 'b.py').write_bytes(b'b')
            original = os.open
            calls = []

            def grow_before_read(path, *args, **kwargs):
                if Path(path).name == 'a.py':
                    Path(path).write_bytes(b'x = 1\n')
                    calls.append(Path(path).name)
                elif Path(path).name == 'b.py':
                    calls.append(Path(path).name)
                return original(path, *args, **kwargs)

            with patch('play_anything.core.repository_graph.os.open', grow_before_read):
                graph = build_repository_graph(root, max_total_source_bytes=1)
            self.assertEqual(calls, ['a.py'])
            self.assertEqual(graph['analysis']['source_bytes_read'], 2)
            self.assertEqual(graph['analysis']['source_budget_exceeded_files'], 2)
            self.assertEqual(graph['summary']['files'], 2)

    def test_invalid_byte_caps_are_rejected_before_filesystem_access(self):
        for cap in [True, False, 0, -1, 1.5, sys.maxsize, sys.maxsize + 1]:
            with self.subTest(cap=cap), patch('play_anything.core.repository_graph.Path.resolve', side_effect=AssertionError('filesystem access')):
                with self.assertRaises(ValueError):
                    build_repository_graph('missing', max_file_bytes=cap)

    def test_huge_valid_cap_reads_small_file_without_preallocation(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'small.py'
            source.write_text('def small(): return 1\n')
            self.assertEqual(_read_capped_source(source, sys.maxsize - 1), source.read_bytes())
            graph = build_repository_graph(directory, max_file_bytes=sys.maxsize - 1)
            self.assertTrue(any(node['name'] == 'small' for node in graph['nodes']))
            budget_graph = build_repository_graph(
                directory, max_total_source_bytes=sys.maxsize - 1,
            )
            self.assertEqual(budget_graph['analysis']['source_bytes_read'], source.stat().st_size)
            self.assertTrue(any(node['name'] == 'small' for node in budget_graph['nodes']))

    def test_capped_reader_returns_one_lookahead_byte_and_handles_multichunk_source(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source.bin'
            source.write_bytes(b'x' * 150000)
            self.assertEqual(len(_read_capped_source(source, 100000)), 100001)
            self.assertEqual(_read_capped_source(source, 200000), source.read_bytes())

    def test_zero_budget_empty_source_is_parsed_without_opening_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'empty.py').write_bytes(b'')
            with patch('play_anything.core.repository_graph._read_capped_source') as reader:
                graph = build_repository_graph(root, max_total_source_bytes=0)

        reader.assert_not_called()
        self.assertEqual(graph['analysis']['analyzed_files'], 1)
        self.assertEqual(graph['analysis']['source_bytes_read'], 0)

    def test_partial_read_failure_keeps_actual_source_byte_count(self):
        class FailingReader:
            def __init__(self):
                self.reads = 0

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _size):
                self.reads += 1
                if self.reads == 1:
                    return b'x=1\n'
                raise PermissionError('read interrupted')

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root.resolve() / 'a.py'
            source.write_bytes(b'x=1\n')
            reader = FailingReader()

            def partial_open(descriptor, *_args, **_kwargs):
                os.close(descriptor)
                return reader

            with patch('play_anything.core.repository_graph.os.fdopen', side_effect=partial_open):
                graph = build_repository_graph(root, max_total_source_bytes=4)

        self.assertEqual(graph['analysis']['unreadable_files'], 1)
        self.assertEqual(graph['analysis']['source_bytes_read'], 4)
        self.assertTrue(graph['analysis']['source_budget_exhausted'])
        self.assertFalse(graph['analysis']['complete'])

    def test_source_file_and_directory_symlinks_are_not_analyzed(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as external:
            root, outside = Path(directory), Path(external)
            (outside / 'secret.py').write_text('def secret(): pass\n')
            (outside / 'nested').mkdir()
            (outside / 'nested' / 'hidden.py').write_text('def hidden(): pass\n')
            try:
                (root / 'file-link.py').symlink_to(outside / 'secret.py')
                (root / 'dir-link').symlink_to(outside / 'nested', target_is_directory=True)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f'symlinks unavailable: {type(exc).__name__}')

            graph = build_repository_graph(root, max_total_source_bytes=100)

        paths = {node.get('path') for node in graph['nodes'] if node['kind'] == 'file'}
        self.assertEqual(paths, set())
        self.assertEqual(graph['analysis']['source_bytes_read'], 0)
