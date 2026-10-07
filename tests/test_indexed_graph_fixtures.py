"""Reproducible fixture provenance and no-clobber acceptance checks."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.generate_indexed_graph_fixtures import generate_fixtures


class IndexedGraphFixtures(unittest.TestCase):
    def test_exports_have_real_relationships_and_identifiable_mutations(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'fixtures'
            manifest = generate_fixtures(output)
            self.assertEqual(manifest['evidence_type'], 'synthetic_index_cli_fixture')
            for record in manifest['files']:
                data = (output / record['name']).read_bytes()
                self.assertEqual(len(data), record['bytes'])
                self.assertEqual(hashlib.sha256(data).hexdigest(), record['sha256'])
                self.assertNotIn(directory.encode(), data)
            page = json.loads((output / 'page-0.json').read_text())
            self.assertEqual({node['id'] for node in page['nodes']}, {'file:a.py', 'file:b.py'})
            self.assertEqual([(edge['source'], edge['target'], edge['relation']) for edge in page['edges']],
                             [('file:a.py', 'file:b.py', 'imports')])
            self.assertEqual(page['coverage']['omitted_cross_page_edges'], 1)
            self.assertTrue(page['coverage']['has_next'])
            invalid = json.loads((output / 'invalid-coverage.json').read_text())
            self.assertEqual(invalid['coverage']['returned_nodes'], len(invalid['nodes']) + 1)
            hostile = json.loads((output / 'hostile-label.json').read_text())
            self.assertEqual(hostile['name'], 'hostile-label-fixture')
            self.assertIn('<script>', hostile['nodes'][0]['name'])

    def test_existing_directory_file_and_symlink_are_never_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            existing = base / 'existing'
            existing.mkdir()
            sentinel = existing / 'keep.txt'
            sentinel.write_text('preserve')
            file = base / 'file'
            file.write_text('preserve')
            link = base / 'link'
            link.symlink_to(base / 'not-created')
            for target in [existing, file, link]:
                with self.subTest(target=target), self.assertRaises(ValueError):
                    generate_fixtures(target)
            self.assertEqual(sentinel.read_text(), 'preserve')
            self.assertEqual(file.read_text(), 'preserve')
            self.assertTrue(link.is_symlink())
            self.assertFalse((base / 'not-created').exists())


if __name__ == '__main__':
    unittest.main()
