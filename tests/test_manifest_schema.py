from copy import deepcopy
import json
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit
import unittest

from play_anything.core.realm_studio import RealmManifest, RealmStudioEngine, SandboxTier


class ManifestSchemaTests(unittest.TestCase):
    def setUp(self):
        self.studio = RealmStudioEngine()
        self.manifest = self.studio.create_template_manifest("Example Realm", "author", "https://example.com/repo")
        self.data = json.loads(self.manifest.to_json())

    def test_schema_export_matches_checked_in_artifact(self):
        path = Path(__file__).resolve().parents[1] / "schemas/realm-manifest.schema.json"
        self.assertEqual(json.loads(path.read_text()), RealmManifest.json_schema())
        schema = RealmManifest.json_schema()
        schema["$defs"].clear()
        self.assertTrue(RealmManifest.json_schema()["$defs"])

    def test_round_trip_and_no_input_mutation(self):
        before = deepcopy(self.data)
        restored = RealmManifest.from_dict(self.data)
        self.assertEqual(self.data, before)
        self.assertIs(type(self.data["requirements"]["sandbox_tier"]), str)
        restored.controls.keybindings["new"] = "N"
        self.assertEqual(self.data, before)
        self.assertEqual(RealmManifest.from_json(self.manifest.to_json()).to_dict(), self.manifest.to_dict())

    def test_optional_fields_and_nested_defaults(self):
        for key in ("evolution", "evaluation", "onboarding_gate", "created_at"):
            del self.data[key]
        self.data["requirements"] = {"target_language": "Python", "min_runtime_version": "3.10"}
        for key in ("controls", "benchmarks", "punishments", "monetization"):
            self.data[key] = {}
        restored = RealmManifest.from_dict(self.data)
        self.assertEqual(restored.requirements.sandbox_tier, SandboxTier.DOCKER_CONTAINER)
        self.assertEqual(restored.onboarding_gate.map_id, restored.id)
        self.assertTrue(self.studio.validate_manifest(restored)["valid"])

    def test_invalid_nested_fields_report_paths(self):
        cases = [
            ("requirements", "max_memory_mb", True),
            ("requirements", "max_memory_mb", 1.5),
            ("requirements", "sandbox_tier", "unknown"),
            ("controls", "allow_voice_commands", "yes"),
            ("controls", "keybindings", {"inspect": 42}),
            ("evaluation", "judge_models", [1]),
            ("evaluation", "confidence_interval_pct", float("nan")),
            ("evaluation", "confidence_interval_pct", float("inf")),
            ("requirements", "unexpected", 1),
        ]
        for section, field, value in cases:
            with self.subTest(section=section, field=field, value=value):
                data = deepcopy(self.data)
                data[section][field] = value
                with self.assertRaises(ValueError) as error:
                    RealmManifest.from_dict(data)
                self.assertIn(f"$.{section}.{field}", str(error.exception))

    def test_missing_unknown_and_wrong_top_level(self):
        for data in ([], None, {**self.data, "unknown": 1},
                     {key: value for key, value in self.data.items() if key != "title"}):
            with self.subTest(data_type=type(data).__name__):
                with self.assertRaises(ValueError):
                    RealmManifest.from_dict(data)
        with self.assertRaises(ValueError):
            RealmManifest.from_json("{bad json}")

    def test_structural_and_business_rules_remain_separate(self):
        self.manifest.objectives = []
        self.assertEqual(RealmManifest.validate_dict(self.manifest.to_dict()), [])
        self.assertFalse(self.studio.validate_manifest(self.manifest)["valid"])
        self.manifest.requirements.max_memory_mb = "invalid"
        result = self.studio.validate_manifest(self.manifest)
        self.assertFalse(result["valid"])
        self.assertIn("$.requirements.max_memory_mb", result["errors"][0])
        with self.assertRaises(ValueError):
            self.manifest.to_json()

    def test_published_share_url_keeps_arbitrary_slug_in_one_path_segment(self):
        ordinary = self.studio.publish_realm(self.manifest)
        self.assertEqual(ordinary["share_url"], "playanything://realms/example-realm")

        self.manifest.slug = "café 🌍/name?query=1#fragment%2F"
        published = self.studio.publish_realm(self.manifest)
        parsed = urlsplit(published["share_url"])
        encoded_slug = parsed.path.removeprefix("/")
        self.assertEqual(parsed.scheme, "playanything")
        self.assertEqual(parsed.netloc, "realms")
        self.assertEqual(parsed.path, "/" + quote(self.manifest.slug, safe=""))
        self.assertEqual(parsed.query, "")
        self.assertEqual(parsed.fragment, "")
        self.assertEqual(unquote(encoded_slug), self.manifest.slug)

    def test_json_schema_integer_semantics(self):
        self.data["requirements"]["max_memory_mb"] = 512.0
        self.assertEqual(RealmManifest.validate_dict(self.data), [])
