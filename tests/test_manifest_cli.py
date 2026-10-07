"""Subprocess coverage for the manifest CLI commands."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from play_anything.core.realm_studio import RealmStudioEngine


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ManifestCliTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "play_anything.cli", *args],
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def write_manifest(self, payload):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        path = Path(temp_dir.name) / "manifest.json"
        path.write_text(payload, encoding="utf-8")
        return path

    def valid_payload(self):
        manifest = RealmStudioEngine().create_template_manifest(
            "CLI Contract Realm", "author", "https://example.com/repo"
        )
        return manifest.to_json()

    def test_manifest_schema_outputs_parseable_draft_2020_12_json(self):
        result = self.run_cli("manifest-schema")
        self.assertEqual(result.returncode, 0, result.stderr)
        schema = json.loads(result.stdout)
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(schema["title"], "Play Anything Realm Manifest")

    def test_validate_manifest_accepts_valid_manifest(self):
        path = self.write_manifest(self.valid_payload())
        result = self.run_cli("validate-manifest", str(path))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("valid", result.stdout.lower())

    def test_validate_manifest_rejects_unknown_schema_key(self):
        data = json.loads(self.valid_payload())
        data["unexpected"] = True
        path = self.write_manifest(json.dumps(data))
        result = self.run_cli("validate-manifest", str(path))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown field", result.stderr.lower())
        self.assertIn("unexpected", result.stderr)

    def test_validate_manifest_rejects_invalid_json_and_duplicate_keys(self):
        cases = (
            "{broken",
            self.valid_payload().replace(
                '"title": "CLI Contract Realm"',
                '"title": 7, "title": "CLI Contract Realm"',
                1,
            ),
        )
        for payload in cases:
            with self.subTest(payload=payload[:20]):
                path = self.write_manifest(payload)
                result = self.run_cli("validate-manifest", str(path))
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("invalid manifest", result.stderr.lower())

    def test_validate_manifest_rejects_semantic_errors(self):
        data = json.loads(self.valid_payload())
        data["objectives"] = []
        path = self.write_manifest(json.dumps(data))
        result = self.run_cli("validate-manifest", str(path))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("objective", result.stderr.lower())

    def test_validate_manifest_reports_missing_file(self):
        result = self.run_cli("validate-manifest", "/no/such/realm-manifest.json")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unable to read", result.stderr.lower())
        self.assertIn("realm-manifest.json", result.stderr)

    def test_root_wrapper_propagates_error_status(self):
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "cli.py"), "unknown-command"],
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("unknown command", result.stderr.lower())

    def test_root_wrapper_propagates_manifest_argument_status(self):
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "cli.py"), "manifest-schema", "extra"],
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("usage", result.stderr.lower())

    def test_bad_arguments_fail_and_existing_help_remains(self):
        for args in (("manifest-schema", "extra"), ("validate-manifest",)):
            with self.subTest(args=args):
                result = self.run_cli(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("usage", result.stderr.lower())
        help_result = self.run_cli("--help")
        self.assertEqual(help_result.returncode, 0)
        self.assertIn("benchmark-all", help_result.stdout)


if __name__ == "__main__":
    unittest.main()
