from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from play_anything.core.repository_graph import build_repository_graph


class RepositoryGraphTests(unittest.TestCase):
    def graph(self, files, **options):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for name, text in files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
            return build_repository_graph(root, **options)

    def test_calls_imports_inheritance_recursion_and_containment(self):
        g = self.graph({'pkg/__init__.py':'', 'pkg/base.py':'class Base: pass\ndef helper(): return 1\n',
            'pkg/app.py':'from .base import Base, helper as run\nclass Child(Base):\n def work(self): return run()\ndef recursive(): return recursive()\n'})
        nodes={n['id']:n for n in g['nodes']}
        relations={(nodes[e['source']]['name'],nodes[e['target']]['name'],e['relation']) for e in g['edges']}
        self.assertIn(('Child','Base','inherits'), relations)
        self.assertIn(('Child.work','helper','calls'),relations)
        self.assertIn(('recursive','recursive','calls'),relations)
        self.assertIn('contains',{e['relation'] for e in g['edges']})

    def test_shadowed_parameter_not_falsely_resolved(self):
        g=self.graph({'main.py':'def target(): pass\ndef caller(target): target()\n'})
        self.assertFalse(any(e['relation']=='calls' for e in g['edges']))
        self.assertTrue(any(e['expression']=='target' for e in g['unresolved']))

    def test_self_calls_marked_inferred(self):
        g=self.graph({'m.py':'class A:\n def a(self): self.b()\n def b(self): pass\n'})
        self.assertEqual([e['confidence'] for e in g['edges'] if e['relation']=='calls'],['inferred'])

    def test_javascript_hints_and_other_files_visible(self):
        g=self.graph({'a.js':"import {b} from './b.js';\nfunction run() {}",'b.js':'export function b() {}','map.json':'{}'})
        self.assertEqual(g['summary']['files'],3)
        self.assertTrue(any(e['relation']=='imports' and e['confidence']=='inferred' for e in g['edges']))
        self.assertEqual(g['summary']['functions'],2)

    def test_limits_and_bad_syntax_are_reported(self):
        exact = self.graph({'a.py': 'pass'}, max_files=1)
        self.assertFalse(exact['analysis']['file_limit_reached'])
        g=self.graph({'a.py':'def broken(', 'b.py':'pass'},max_files=1)
        self.assertTrue(g['truncated'])
        self.assertTrue(g['warnings'])
        with self.assertRaises(ValueError): self.graph({},max_symbols=0)

    def test_exact_symbol_limit_is_complete_until_an_extra_symbol_is_omitted(self):
        exact = self.graph({'a.py': 'def one(): pass\n'}, max_symbols=1)
        self.assertEqual(exact['summary']['functions'], 1)
        self.assertFalse(exact['analysis']['symbol_limit_reached'])

        overflow = self.graph({'a.py': 'def one(): pass\ndef two(): pass\n'}, max_symbols=1)
        self.assertEqual(overflow['summary']['functions'], 1)
        self.assertTrue(overflow['analysis']['symbol_limit_reached'])

    def test_directory_walk_errors_propagate(self):
        with tempfile.TemporaryDirectory() as directory:
            def failed_walk(root, *, onerror):
                onerror(PermissionError('fixture traversal failure'))
                return iter(())

            with patch('play_anything.core.repository_graph.os.walk', side_effect=failed_walk):
                with self.assertRaisesRegex(PermissionError, 'fixture traversal failure'):
                    build_repository_graph(directory)

    def test_source_byte_cap_is_inclusive_and_reported(self):
        exact = self.graph({'a.py': 'x=1\n'}, max_file_bytes=4)
        self.assertEqual(exact['analysis']['analyzed_files'], 1)
        self.assertEqual(exact['analysis']['max_file_bytes'], 4)
        self.assertEqual(exact['analysis']['too_large_files'], 0)

        oversized = self.graph({'a.py': 'x=1\ny=2\n'}, max_file_bytes=4)
        self.assertEqual(oversized['analysis']['too_large_files'], 1)
        self.assertEqual(oversized['analysis']['max_file_bytes'], 4)
        self.assertFalse(oversized['analysis']['complete'])

    def test_nested_functions_resolve_and_output_is_deterministic(self):
        files={'x.py':'def outer():\n def inner(): pass\n inner()\n'}
        g=self.graph(files)
        self.assertEqual(len([e for e in g['edges'] if e['relation']=='calls']),1)
