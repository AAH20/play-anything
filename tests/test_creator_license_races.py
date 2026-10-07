"""Race contracts for Creator's bounded license-document preview."""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from play_anything.creator_server import inspect_repository


class CreatorLicenseRaceTests(unittest.TestCase):
    def test_replacing_candidate_with_symlink_before_open_never_returns_target_text(self):
        secret = "PRIVATE-OUTSIDE-LICENSE-CONTENT"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            root.mkdir()
            candidate = root / "LICENSE"
            candidate.write_text("ordinary license text", encoding="utf-8")
            outside = Path(temporary) / "outside.txt"
            outside.write_text(secret, encoding="utf-8")
            real_open = os.open
            swapped = False

            def swap_before_descriptor_open(path, flags, *args, **kwargs):
                nonlocal swapped
                if Path(os.fsdecode(path)) == candidate and not swapped:
                    candidate.unlink()
                    candidate.symlink_to(outside)
                    swapped = True
                return real_open(path, flags, *args, **kwargs)

            with patch("play_anything.creator_server.os.open",
                       side_effect=swap_before_descriptor_open):
                report = inspect_repository(root, "fixture")

        self.assertTrue(swapped, "license preview did not use the descriptor-open boundary")
        self.assertNotIn(secret, json.dumps(report))
        self.assertEqual(report["licenses"], [])
        self.assertIn("LICENSE", report["analysis"]["license_read_errors"])


if __name__ == "__main__":
    unittest.main()
