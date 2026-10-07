"""Cross-version failure contracts for RealmManifest JSON interchange."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from play_anything.core.realm_studio import RealmManifest, RealmStudioEngine


class ManifestJsonBoundaryTests(unittest.TestCase):
    def setUp(self):
        manifest = RealmStudioEngine().create_template_manifest(
            "Nested JSON probe", "author", "https://example.com/repo"
        )
        data = json.loads(manifest.to_json())
        self.valid_payload = json.dumps(data, separators=(",", ":"))
        description = json.dumps(data["description"])
        deeply_nested = "[" * 3000 + "0" + "]" * 3000
        self.payload = self.valid_payload.replace(
            '"description":' + description,
            '"description":' + deeply_nested,
        )

    def test_deep_json_parser_limit_is_a_manifest_value_error(self):
        with self.assertRaises(ValueError):
            RealmManifest.from_json(self.payload)

    def test_cli_reports_deep_json_as_invalid_manifest_without_traceback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "deep.json"
            path.write_text(self.payload, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-m", "play_anything.cli", "validate-manifest", str(path)],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("Invalid manifest:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_json_integer_fields_use_exact_decimal_token_semantics(self):
        marker = '"max_memory_mb":512'
        self.assertIn(marker, self.valid_payload)
        rounded_noninteger = self.valid_payload.replace(
            marker,
            '"max_memory_mb":512.0000000000000000000000000000000000000000000000000000000000000000001',
            1,
        )
        with self.assertRaisesRegex(ValueError, r"requirements\.max_memory_mb: expected integer"):
            RealmManifest.from_json(rounded_noninteger)

        for token in ("512.0", "5.12e2"):
            with self.subTest(token=token):
                exact_integer = self.valid_payload.replace(marker, '"max_memory_mb":' + token, 1)
                manifest = RealmManifest.from_json(exact_integer)
                self.assertEqual(manifest.requirements.max_memory_mb, 512.0)
                self.assertIs(type(manifest.requirements.max_memory_mb), float)

        large_exact_token = self.valid_payload.replace(
            marker, '"max_memory_mb":9007199254740993.0', 1
        )
        manifest = RealmManifest.from_json(large_exact_token)
        self.assertEqual(manifest.requirements.max_memory_mb, 9007199254740993)
        self.assertIs(type(manifest.requirements.max_memory_mb), int)
        self.assertEqual(
            json.loads(manifest.to_json())["requirements"]["max_memory_mb"],
            9007199254740993,
        )

        exponent_integer = self.valid_payload.replace(marker, '"max_memory_mb":1e309', 1)
        exponent_manifest = RealmManifest.from_json(exponent_integer)
        self.assertEqual(exponent_manifest.requirements.max_memory_mb, 10 ** 309)
        self.assertEqual(
            json.loads(exponent_manifest.to_json())["requirements"]["max_memory_mb"],
            10 ** 309,
        )

        oversized_integer = self.valid_payload.replace(
            marker, '"max_memory_mb":1e1000000000', 1
        )
        with self.assertRaisesRegex(ValueError, "runtime digit limit"):
            RealmManifest.from_json(oversized_integer)

    def test_large_integer_counters_round_trip_exactly(self):
        data = json.loads(self.valid_payload)
        exact_counter = 10 ** 1000
        data["objectives"][0]["xp_reward"] = exact_counter
        original = data["objectives"][0]["xp_reward"]

        restored = RealmManifest.from_json(json.dumps(data))

        self.assertEqual(restored.objectives[0].xp_reward, original)
        self.assertEqual(
            json.loads(restored.to_json())["objectives"][0]["xp_reward"],
            original,
        )

    def test_float_fields_remain_plain_floats_and_overflow_is_rejected(self):
        valid = self.valid_payload.replace(
            '"creator_rev_share_pct":70.0', '"creator_rev_share_pct":70.25', 1
        )
        manifest = RealmManifest.from_json(valid)
        self.assertEqual(manifest.monetization.creator_rev_share_pct, 70.25)
        self.assertIs(type(manifest.monetization.creator_rev_share_pct), float)

        overflow = self.valid_payload.replace(
            '"confidence_interval_pct":95.0', '"confidence_interval_pct":1e999', 1
        )
        with self.assertRaisesRegex(ValueError, r"evaluation\.confidence_interval_pct: expected number"):
            RealmManifest.from_json(overflow)

    def test_json_royalty_bounds_use_exact_decimal_tokens(self):
        royalty_rule = RealmManifest.json_schema()["$defs"]["RealmMonetizationConfig"][
            "properties"]["creator_rev_share_pct"]
        self.assertEqual(royalty_rule["minimum"], 0.0)
        self.assertEqual(royalty_rule["maximum"], 85.0)

        marker = '"creator_rev_share_pct":70.0'
        just_over_max = self.valid_payload.replace(
            marker,
            '"creator_rev_share_pct":85.0000000000000000000000000000000000000000000000000000000000000000001',
            1,
        )
        with self.assertRaisesRegex(ValueError, r"creator_rev_share_pct:.*85"):
            RealmManifest.from_json(just_over_max)

        just_under_min = self.valid_payload.replace(
            marker,
            '"creator_rev_share_pct":-0.0000000000000000000000000000000000000000000000000000000000000000001',
            1,
        )
        with self.assertRaisesRegex(ValueError, r"creator_rev_share_pct:.*0"):
            RealmManifest.from_json(just_under_min)

        for token in ("0.0", "85.0"):
            with self.subTest(token=token):
                valid_boundary = self.valid_payload.replace(
                    marker, '"creator_rev_share_pct":' + token, 1
                )
                manifest = RealmManifest.from_json(valid_boundary)
                self.assertEqual(manifest.monetization.creator_rev_share_pct, float(token))
                self.assertIs(type(manifest.monetization.creator_rev_share_pct), float)

    def test_royalty_bounds_handle_decimal_exponents_outside_decimal_context(self):
        marker = '"creator_rev_share_pct":70.0'
        exponent = "9" * 30

        negative_tiny = self.valid_payload.replace(
            marker, '"creator_rev_share_pct":-1e-' + exponent, 1
        )
        with self.assertRaisesRegex(ValueError, r"creator_rev_share_pct:.*at least 0"):
            RealmManifest.from_json(negative_tiny)
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "negative-underflow.json"
            path.write_text(negative_tiny, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-m", "play_anything.cli", "validate-manifest", str(path)],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(result.returncode, 1)
        self.assertIn("creator_rev_share_pct", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

        # Positive values this small satisfy the inclusive zero lower bound;
        # the public dataclass still exposes its normal float representation.
        positive_tiny = self.valid_payload.replace(
            marker, '"creator_rev_share_pct":1e-' + exponent, 1
        )
        manifest = RealmManifest.from_json(positive_tiny)
        self.assertEqual(manifest.monetization.creator_rev_share_pct, 0.0)
        self.assertIs(type(manifest.monetization.creator_rev_share_pct), float)

        # A signed zero is exactly zero despite an out-of-context exponent.
        signed_zero = self.valid_payload.replace(
            marker, '"creator_rev_share_pct":-0e' + exponent, 1
        )
        manifest = RealmManifest.from_json(signed_zero)
        self.assertEqual(manifest.monetization.creator_rev_share_pct, 0.0)
        self.assertIs(type(manifest.monetization.creator_rev_share_pct), float)

        positive_overflow = self.valid_payload.replace(
            marker, '"creator_rev_share_pct":1e' + exponent, 1
        )
        with self.assertRaisesRegex(ValueError, r"creator_rev_share_pct: expected number"):
            RealmManifest.from_json(positive_overflow)


if __name__ == "__main__":
    unittest.main()
