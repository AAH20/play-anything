"""Root validation must preserve filesystem errors during an indexed rebuild."""
import errno
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from play_anything.adapters.repository_store import SQLiteRepositoryStore


class RepositoryStoreRootErrorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / "repo"
        self.root.mkdir()
        self.database = self.base / "index.sqlite"

    def test_missing_and_non_directory_roots_keep_distinct_errors(self):
        with SQLiteRepositoryStore(self.database) as store:
            with self.assertRaises(FileNotFoundError):
                store.rebuild(self.base / "missing")

            file_root = self.base / "not-a-directory"
            file_root.write_text("source", encoding="utf-8")
            with self.assertRaises(NotADirectoryError):
                store.rebuild(file_root)

    def test_permission_stat_error_is_not_reported_as_missing_root(self):
        root_key = str(self.root.resolve())
        real_stat = os.stat

        def deny_root(path, *args, **kwargs):
            if os.fspath(path) == root_key:
                raise PermissionError("repository root access denied")
            return real_stat(path, *args, **kwargs)

        with SQLiteRepositoryStore(self.database) as store:
            with patch("play_anything.adapters.repository_store.os.stat",
                       side_effect=deny_root):
                with self.assertRaisesRegex(PermissionError, "repository root access denied"):
                    store.rebuild(self.root)

    def test_root_stat_failure_preserves_the_previously_published_generation(self):
        (self.root / "old.py").write_text("value = 1\n", encoding="utf-8")
        root_key = str(self.root.resolve())
        real_stat = os.stat

        def deny_root(path, *args, **kwargs):
            if os.fspath(path) == root_key:
                raise PermissionError("repository root access denied")
            return real_stat(path, *args, **kwargs)

        with SQLiteRepositoryStore(self.database) as store:
            before = store.rebuild(self.root, max_files=None)
            with patch("play_anything.adapters.repository_store.os.stat",
                       side_effect=deny_root):
                with self.assertRaises(PermissionError):
                    store.rebuild(self.root, max_files=None)
            after = store.status(self.root)
            files_after = store.files(self.root)

        self.assertEqual(after["generation"], before["generation"])
        self.assertEqual(after["file_count"], 1)
        self.assertEqual([item["path"] for item in files_after], ["old.py"])

    def test_cyclic_root_alias_is_reported_as_an_os_error(self):
        loop = self.base / "root-loop"
        try:
            loop.symlink_to(loop)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink creation is unavailable")

        with SQLiteRepositoryStore(self.database) as store:
            with self.assertRaises(OSError) as raised:
                store.rebuild(loop)
        self.assertEqual(raised.exception.errno, errno.ELOOP)

    def test_cyclic_database_alias_is_reported_as_an_os_error(self):
        loop = self.base / "database-loop.sqlite"
        try:
            loop.symlink_to(loop)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink creation is unavailable")

        with self.assertRaises(OSError) as raised:
            with SQLiteRepositoryStore(loop):
                pass
        self.assertEqual(raised.exception.errno, errno.ELOOP)


if __name__ == "__main__":
    unittest.main()
