"""
Unit tests for Realm Studio & Creator Economy Engine (Fortnite / Roblox for Developers).
Uses standard library unittest for zero-dependency portability.
"""

import unittest
from play_anything.core.realm_studio import (
    RealmStudioEngine,
    RealmManifest,
    GameMode,
    ControlScheme,
    SandboxTier,
    AntiCheatStrictness,
    AccessType
)


class TestRealmStudio(unittest.TestCase):

    def setUp(self):
        self.studio = RealmStudioEngine()

    def test_create_and_validate_template_manifest(self):
        manifest = self.studio.create_template_manifest(
            title="Apollo Auth Fortress",
            author="SovereignDev",
            repository_url="https://github.com/example/auth-fortress.git",
            game_mode=GameMode.BOSS_RAID
        )

        self.assertTrue(manifest.id.startswith("realm_"))
        self.assertEqual(manifest.title, "Apollo Auth Fortress")
        self.assertEqual(manifest.slug, "apollo-auth-fortress")
        self.assertEqual(manifest.requirements.sandbox_tier, SandboxTier.DOCKER_CONTAINER)

        val = self.studio.validate_manifest(manifest)
        self.assertTrue(val["valid"])
        self.assertEqual(len(val["errors"]), 0)

    def test_publish_and_payout_simulation(self):
        manifest = self.studio.create_template_manifest(
            title="Distributed Saga Gauntlet",
            author="CloudWarrior",
            repository_url="https://github.com/example/saga-gauntlet.git",
            game_mode=GameMode.SPEEDRUN_REFACTOR
        )
        manifest.monetization.access_type = AccessType.PREMIUM_TICKET
        manifest.monetization.ticket_price_tokens = 50
        manifest.monetization.creator_rev_share_pct = 70.0

        pub = self.studio.publish_realm(manifest)
        self.assertEqual(pub["status"], "PUBLISHED")
        self.assertEqual(pub["creator_rev_share"], "70.0%")

        # Simulate 5,000 players with 80% completion rate, 50,000 tokens ticket revenue
        payout = self.studio.simulate_payout_distribution(
            realm_id=manifest.id,
            total_plays=5000,
            completion_rate=0.80,
            ticket_sales_revenue_tokens=50000,
            engagement_pool_size_tokens=100000
        )

        self.assertEqual(payout["direct_creator_tokens"], 35000)  # 70% of 50,000
        self.assertEqual(payout["platform_fee_tokens"], 15000)   # 30% of 50,000
        self.assertGreater(payout["engagement_pool_tokens"], 0)
        self.assertGreater(payout["total_creator_tokens"], 35000)
        self.assertGreater(payout["estimated_devex_usd"], 350.0)  # 1 token = $0.01

    def test_serialization_cycle(self):
        manifest = self.studio.create_template_manifest(
            title="Zero-Day Hunting Grounds",
            author="WhiteHat",
            repository_url="https://github.com/example/ctf-zero-day.git",
            game_mode=GameMode.CAPTURE_THE_FLAG
        )

        data = manifest.to_dict()
        self.assertIsInstance(data, dict)
        reloaded = RealmManifest.from_dict(data)
        self.assertEqual(reloaded.title, manifest.title)
        self.assertEqual(reloaded.game_mode, GameMode.CAPTURE_THE_FLAG)
        self.assertEqual(reloaded.benchmarks.anti_cheat_mode, AntiCheatStrictness.STRICT)


if __name__ == "__main__":
    unittest.main()
