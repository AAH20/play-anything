"""Filesystem root errors should be explicit before an index cache is opened."""
import errno
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from play_anything.adapters.repository_index import iter_repository_summaries


class RepositoryIndexRootErrorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)

    def test_missing_root_raises_before_creating_the_cache(self):
        missing = self.base / "missing"
        cache = self.base / "cache.sqlite"

        with self.assertRaises(FileNotFoundError):
            list(iter_repository_summaries(missing, cache_path=cache))

        self.assertFalse(cache.exists())

    def test_regular_file_root_is_not_treated_as_an_empty_repository(self):
        file_root = self.base / "not-a-directory"
        file_root.write_text("source", encoding="utf-8")

        with self.assertRaises(NotADirectoryError):
            list(iter_repository_summaries(file_root))

    def test_permission_error_propagates_before_creating_the_cache(self):
        root = self.base / "repo"
        root.mkdir()
        cache = self.base / "permission-cache.sqlite"
        root_key = os.fspath(root)
        real_stat = os.stat

        def deny_root(path, *args, **kwargs):
            if os.fspath(path) == root_key:
                raise PermissionError("repository root denied")
            return real_stat(path, *args, **kwargs)

        with patch("play_anything.adapters.repository_index.os.stat", side_effect=deny_root):
            with self.assertRaisesRegex(PermissionError, "repository root denied"):
                list(iter_repository_summaries(root, cache_path=cache))

        self.assertFalse(cache.exists())

    def test_symlink_directory_alias_keeps_repository_relative_paths(self):
        root = self.base / "repo"
        root.mkdir()
        (root / "a.py").write_text("value = 1\n", encoding="utf-8")
        alias = self.base / "repo-alias"
        try:
            alias.symlink_to(root, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink creation is unavailable")

        summaries = list(iter_repository_summaries(alias))
        self.assertEqual([summary["path"] for summary in summaries], ["a.py"])

    def test_symlink_loop_root_raises_os_error_before_cache_creation(self):
        loop = self.base / "loop"
        try:
            loop.symlink_to(loop)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink creation is unavailable")
        cache = self.base / "loop-cache.sqlite"

        with self.assertRaises(OSError) as raised:
            list(iter_repository_summaries(loop, cache_path=cache))

        self.assertEqual(raised.exception.errno, errno.ELOOP)
        self.assertFalse(cache.exists())

    def test_symlink_loop_cache_path_raises_os_error_on_supported_pathlib_versions(self):
        root = self.base / "repo"
        root.mkdir()
        (root / "a.py").write_text("value = 1\n", encoding="utf-8")
        loop = self.base / "cache-loop"
        try:
            loop.symlink_to(loop)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink creation is unavailable")

        with self.assertRaises(OSError) as raised:
            list(iter_repository_summaries(root, cache_path=loop))

        self.assertEqual(raised.exception.errno, errno.ELOOP)
        self.assertTrue(loop.is_symlink())

    def test_symlink_loop_in_cache_parent_is_normalized(self):
        root = self.base / "repo"
        root.mkdir()
        loop = self.base / "cache-loop-parent"
        try:
            loop.symlink_to(loop, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink creation is unavailable")

        with self.assertRaises(OSError) as raised:
            list(iter_repository_summaries(root, cache_path=loop / "cache.sqlite"))

        self.assertEqual(raised.exception.errno, errno.ELOOP)

    def test_ordinary_cache_open_failure_still_propagates_as_sqlite_error(self):
        root = self.base / "repo"
        root.mkdir()
        (root / "a.py").write_text("value = 1\n", encoding="utf-8")
        cache = self.base / "missing-parent" / "cache.sqlite"

        with self.assertRaises(sqlite3.OperationalError):
            list(iter_repository_summaries(root, cache_path=cache))

        self.assertFalse(cache.parent.exists())


if __name__ == "__main__":
    unittest.main()
