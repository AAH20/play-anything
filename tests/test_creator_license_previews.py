"""Deterministic bounded document previews with explicit omission evidence."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from play_anything.creator_server import inspect_repository


class CreatorLicensePreviewTests(unittest.TestCase):
    def test_default_selects_first_32_matching_documents_and_discloses_omissions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for number in reversed(range(35)):
                (root / f'LICENSE-{number:02d}').write_text(f'Document {number}')
            (root / 'unrelated.txt').write_text('ignored preview')
            report = inspect_repository(root, 'fixture')
        self.assertEqual([p['name'] for p in report['licenses']],
                         [f'LICENSE-{n:02d}' for n in range(32)])
        analysis = report['analysis']
        self.assertEqual(analysis['license_files_seen'], 35)
        self.assertEqual(analysis['license_file_limit'], 32)
        self.assertTrue(analysis['license_file_limit_reached'])
        self.assertTrue(analysis['truncated'])
        self.assertFalse(analysis['complete'])
        self.assertTrue(any('selected 32 of 35' in warning for warning in analysis['warnings']))

    def test_character_boundary_is_explicit_and_small_preview_shape_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'LICENSE').write_text('a' * 12000)
            exact = inspect_repository(root, 'fixture')
            (root / 'LICENSE').write_text('a' * 12001)
            truncated = inspect_repository(root, 'fixture')
        self.assertEqual(exact['licenses'][0], {'name': 'LICENSE', 'text': 'a' * 12000})
        self.assertEqual(exact['analysis']['license_preview_truncated_files'], 0)
        self.assertEqual(truncated['licenses'][0]['text'], 'a' * 12000)
        self.assertTrue(truncated['licenses'][0]['text_truncated'])
        self.assertEqual(truncated['analysis']['license_preview_truncated_files'], 1)
        self.assertTrue(any('previews are incomplete' in w for w in truncated['analysis']['warnings']))

    def test_explicit_uncapped_option_retains_all_documents_and_excludes_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for number in range(34):
                (root / f'NOTICE-{number:02d}').write_text('text')
            (root / 'LICENSE-link').symlink_to(root / 'NOTICE-00')
            report = inspect_repository(root, 'fixture', max_license_files=None)
        self.assertEqual(len(report['licenses']), 34)
        self.assertEqual(report['analysis']['license_files_seen'], 34)
        self.assertIsNone(report['analysis']['license_file_limit'])
        self.assertFalse(report['analysis']['license_file_limit_reached'])

    def test_invalid_preview_limits_fail_before_scanning(self):
        for invalid in (True, False, 0, -1, 1.5, 1001, '32'):
            with self.subTest(invalid=invalid), \
                    patch('play_anything.creator_server.iter_repository_summaries') as scan:
                with self.assertRaises(ValueError):
                    inspect_repository(Path('/does/not/exist'), 'fixture', max_license_files=invalid)
                scan.assert_not_called()

    def test_path_changed_to_symlink_after_inventory_is_not_opened_as_a_preview(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / 'unrelated.txt'
            target.write_text('not a license preview')
            linked = root / 'LICENSE'
            linked.symlink_to(target)
            with patch('play_anything.creator_server._license_preview_inventory',
                       return_value=([linked], 1)):
                report = inspect_repository(root, 'fixture')
        self.assertEqual(report['licenses'], [])
        self.assertEqual(report['analysis']['license_read_errors'], ['LICENSE'])
        self.assertFalse(report['analysis']['complete'])
