"""Contract tests for strict RealmManifest JSON interchange."""

import json
from fractions import Fraction
import math
import unittest

from play_anything.core.realm_studio import RealmManifest, RealmStudioEngine


class RealmManifestContractTests(unittest.TestCase):
    def setUp(self):
        manifest = RealmStudioEngine().create_template_manifest(
            "Contract Test Realm", "author", "https://example.com/repo"
        )
        self.payload = manifest.to_json()
        self.data = json.loads(self.payload)

    def test_json_round_trip_preserves_manifest(self):
        restored = RealmManifest.from_json(self.payload)
        self.assertEqual(restored.to_dict(), json.loads(self.payload))
        self.assertEqual(
            RealmManifest.from_json(restored.to_json()).to_dict(),
            restored.to_dict(),
        )

    def test_semantic_validation_rejects_nonpositive_resource_budgets(self):
        self.data["requirements"]["max_memory_mb"] = -1
        self.data["requirements"]["max_cpu_time_ms"] = 0
        self.assertEqual(RealmManifest.validate_dict(self.data), [])

        manifest = RealmManifest.from_dict(self.data)
        result = RealmStudioEngine().validate_manifest(manifest)
        self.assertFalse(result["valid"])
        self.assertTrue(any("max_memory_mb" in error for error in result["errors"]))
        self.assertTrue(any("max_cpu_time_ms" in error for error in result["errors"]))

    def test_structural_and_semantic_validation_reject_negative_creator_revenue_share(self):
        manifest = RealmManifest.from_json(self.payload)
        manifest.monetization.creator_rev_share_pct = -10.0

        structural_errors = RealmManifest.validate_dict(manifest.to_dict())
        self.assertTrue(any("creator_rev_share_pct" in error for error in structural_errors))
        result = RealmStudioEngine().validate_manifest(manifest)
        self.assertFalse(result["valid"])
        self.assertTrue(any("creator_rev_share_pct" in error for error in result["errors"]))
        with self.assertRaisesRegex(ValueError, "creator_rev_share_pct"):
            RealmStudioEngine().publish_realm(manifest)

        studio = RealmStudioEngine()
        mutable_manifest = RealmManifest.from_json(self.payload)
        studio.publish_realm(mutable_manifest)
        studio.published_realms[mutable_manifest.id].monetization.creator_rev_share_pct = -10.0
        with self.assertRaisesRegex(ValueError, "no longer valid.*creator_rev_share_pct"):
            studio.simulate_payout_distribution(
                mutable_manifest.id, total_plays=10, completion_rate=1.0,
                ticket_sales_revenue_tokens=100, engagement_pool_size_tokens=0,
            )

    def test_creator_revenue_share_accepts_the_supported_boundaries(self):
        studio = RealmStudioEngine()
        for percentage in (0.0, 85.0):
            with self.subTest(percentage=percentage):
                manifest = RealmManifest.from_json(self.payload)
                manifest.monetization.creator_rev_share_pct = percentage
                self.assertTrue(studio.validate_manifest(manifest)["valid"])

    def test_publish_snapshots_caller_manifest(self):
        studio = RealmStudioEngine()
        manifest = RealmManifest.from_json(self.payload)
        original_title = manifest.title
        original_share = manifest.monetization.creator_rev_share_pct
        studio.publish_realm(manifest)

        manifest.title = "Changed after publication"
        manifest.monetization.creator_rev_share_pct = 1.0
        payout = studio.simulate_payout_distribution(
            manifest.id, total_plays=0, completion_rate=0.0,
            ticket_sales_revenue_tokens=100, engagement_pool_size_tokens=0,
        )

        self.assertEqual(payout["realm_title"], original_title)
        self.assertEqual(
            payout["direct_creator_tokens"], int(100 * original_share / 100.0)
        )

    def test_payout_rejects_invalid_numeric_inputs(self):
        studio = RealmStudioEngine()
        manifest = RealmManifest.from_json(self.payload)
        studio.publish_realm(manifest)
        valid = {
            "realm_id": manifest.id,
            "total_plays": 10,
            "completion_rate": 0.5,
            "ticket_sales_revenue_tokens": 100,
            "engagement_pool_size_tokens": 50,
        }
        invalid_cases = (
            ("total_plays", True),
            ("total_plays", -1),
            ("completion_rate", True),
            ("completion_rate", float("nan")),
            ("completion_rate", float("inf")),
            ("completion_rate", -0.1),
            ("completion_rate", 1.1),
            ("ticket_sales_revenue_tokens", False),
            ("ticket_sales_revenue_tokens", -1),
            ("engagement_pool_size_tokens", True),
            ("engagement_pool_size_tokens", -1),
        )
        for name, value in invalid_cases:
            with self.subTest(name=name, value=value):
                arguments = dict(valid)
                arguments[name] = value
                with self.assertRaisesRegex(ValueError, name):
                    studio.simulate_payout_distribution(**arguments)

    def test_payout_handles_large_play_counts_and_rejects_nonfinite_settlements(self):
        studio = RealmStudioEngine()
        manifest = RealmManifest.from_json(self.payload)
        studio.publish_realm(manifest)

        result = studio.simulate_payout_distribution(
            manifest.id, total_plays=10 ** 1000, completion_rate=1.0,
            ticket_sales_revenue_tokens=100, engagement_pool_size_tokens=100,
        )
        self.assertTrue(math.isfinite(result["estimated_settlement_usd"]))
        self.assertEqual(result["engagement_pool_tokens"], 15)

        with self.assertRaisesRegex(ValueError, "finite numeric range"):
            studio.simulate_payout_distribution(
                manifest.id, total_plays=0, completion_rate=0.0,
                ticket_sales_revenue_tokens=10 ** 1000,
                engagement_pool_size_tokens=0,
            )

    def test_direct_revenue_share_matches_exact_decimal_floor_and_conserves(self):
        cases = (
            (70.0, 90),
            (33.3, 1000),
            (0.0, 12345),
            (85.0, 9876),
            (33.3, 2 ** 1023),
        )
        for percentage, ticket_tokens in cases:
            with self.subTest(percentage=percentage, ticket_tokens=ticket_tokens):
                studio = RealmStudioEngine()
                manifest = RealmManifest.from_json(self.payload)
                manifest.monetization.creator_rev_share_pct = percentage
                studio.publish_realm(manifest)
                result = studio.simulate_payout_distribution(
                    manifest.id, total_plays=0, completion_rate=0.0,
                    ticket_sales_revenue_tokens=ticket_tokens,
                    engagement_pool_size_tokens=0,
                )

                exact_rate = Fraction(str(percentage)) / 100
                expected_creator = ticket_tokens * exact_rate.numerator // exact_rate.denominator
                self.assertEqual(result["direct_creator_tokens"], expected_creator)
                self.assertEqual(
                    result["direct_creator_tokens"] + result["platform_fee_tokens"],
                    ticket_tokens,
                )

    def test_engagement_payout_matches_exact_capped_factor_and_never_overspends(self):
        cases = (
            (2, 0.5, 1_000_000),
            (15, 0.0, 1_000_000),
            (90, 0.1, 1_000_000),
            (1160, 0.25, 100_000),
            (0, 1.0, 12345),
            (24999, 0.0, 2 ** 1023),
            (25000, 0.0, 1_000_000),
            (50000, 1.0, 999_999),
        )
        for total_plays, completion_rate, pool_tokens in cases:
            with self.subTest(total_plays=total_plays, completion_rate=completion_rate,
                              pool_tokens=pool_tokens):
                studio = RealmStudioEngine()
                manifest = RealmManifest.from_json(self.payload)
                studio.publish_realm(manifest)
                result = studio.simulate_payout_distribution(
                    manifest.id, total_plays=total_plays,
                    completion_rate=completion_rate,
                    ticket_sales_revenue_tokens=0,
                    engagement_pool_size_tokens=pool_tokens,
                )

                rate = Fraction(str(completion_rate))
                weight = Fraction(2, 5) + Fraction(3, 5) * rate
                factor = min(Fraction(1), total_plays * weight / 10_000)
                exact_payout = pool_tokens * Fraction(15, 100) * factor
                expected_payout = exact_payout.numerator // exact_payout.denominator
                self.assertEqual(result["engagement_pool_tokens"], expected_payout)
                self.assertGreaterEqual(result["engagement_pool_tokens"], 0)
                self.assertLessEqual(result["engagement_pool_tokens"], pool_tokens)

    def test_from_json_rejects_duplicate_object_keys(self):
        payload = self.payload.replace(
            '"title": "Contract Test Realm"',
            '"title": 7, "title": "Contract Test Realm"',
            1,
        )
        with self.assertRaisesRegex(ValueError, "(?i)duplicate.*title"):
            RealmManifest.from_json(payload)

    def test_from_json_rejects_duplicate_nested_object_keys(self):
        payload = self.payload.replace(
            '"target_language": "TypeScript / Node.js 20+"',
            '"target_language": 7, "target_language": "TypeScript / Node.js 20+"',
            1,
        )
        with self.assertRaisesRegex(ValueError, "(?i)duplicate.*target_language"):
            RealmManifest.from_json(payload)


if __name__ == "__main__":
    unittest.main()
