"""
Unit tests for Sovereign Realm Studio & Model Evaluation Colosseum.
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
    AccessType,
    ArenaProtocol,
    EvolutionConfig,
    EvaluationConfig,
    ModelArenaEngine
)


class TestRealmStudio(unittest.TestCase):

    def setUp(self):
        self.studio = RealmStudioEngine()

    def test_create_and_validate_template_manifest(self):
        manifest = self.studio.create_template_manifest(
            title="Apollo Auth Fortress",
            author="SovereignArchitect",
            repository_url="https://github.com/example/auth-fortress.git",
            game_mode=GameMode.MODEL_EVAL_COLOSSEUM
        )

        self.assertTrue(manifest.id.startswith("realm_"))
        self.assertEqual(manifest.title, "Apollo Auth Fortress")
        self.assertEqual(manifest.slug, "apollo-auth-fortress")
        self.assertEqual(manifest.requirements.sandbox_tier, SandboxTier.DOCKER_CONTAINER)
        self.assertEqual(manifest.evolution.generation_budget, 50)
        self.assertEqual(manifest.evaluation.arena_protocol, ArenaProtocol.KAGGLE_GAME_ARENA_SWISS)

        val = self.studio.validate_manifest(manifest)
        self.assertTrue(val["valid"])
        self.assertEqual(len(val["errors"]), 0)

    def test_model_arena_pairwise_and_leaderboard(self):
        arena = ModelArenaEngine()
        board = arena.get_leaderboard()
        self.assertGreaterEqual(len(board), 4)

        # Sovereign Agent Apex should be #1 initially
        self.assertEqual(board[0]["model_id"], "sovereign_agent_apex")

        # Simulate match between DeepSeek-R1 and GPT-4o
        prob_deepseek = arena.predict_pairwise_prob("deepseek_r1", "gpt_4o")
        self.assertGreater(prob_deepseek, 0.5)  # DeepSeek Elo > GPT-4o Elo

        # Record DeepSeek victory
        result = arena.record_match_result("deepseek_r1", "gpt_4o", score_a=1.0)
        self.assertGreater(result["model_a"]["delta"], 0)
        self.assertLess(result["model_b"]["delta"], 0)

    def test_publish_and_settlement_simulation(self):
        manifest = self.studio.create_template_manifest(
            title="Distributed Consensus Arena",
            author="SovereignQuant",
            repository_url="https://github.com/example/consensus-arena.git",
            game_mode=GameMode.SPEEDRUN_REFACTOR
        )
        manifest.monetization.access_type = AccessType.PREMIUM_CHALLENGE
        manifest.monetization.ticket_price_tokens = 50
        manifest.monetization.creator_rev_share_pct = 70.0

        pub = self.studio.publish_realm(manifest)
        self.assertEqual(pub["status"], "PUBLISHED")
        self.assertEqual(pub["creator_rev_share"], "70.0%")
        self.assertEqual(pub["eval_protocol"], ArenaProtocol.KAGGLE_GAME_ARENA_SWISS.value)

        # Simulate 5,000 runs with 80% completion rate, 50,000 credits revenue
        settlement = self.studio.simulate_payout_distribution(
            realm_id=manifest.id,
            total_plays=5000,
            completion_rate=0.80,
            ticket_sales_revenue_tokens=50000,
            engagement_pool_size_tokens=100000
        )

        self.assertEqual(settlement["direct_creator_tokens"], 35000)
        self.assertEqual(settlement["platform_fee_tokens"], 15000)
        self.assertGreater(settlement["engagement_pool_tokens"], 0)
        self.assertGreater(settlement["estimated_settlement_usd"], 350.0)

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
        self.assertEqual(reloaded.evolution.population_size, 32)
        self.assertEqual(reloaded.evaluation.arena_protocol, ArenaProtocol.KAGGLE_GAME_ARENA_SWISS)


if __name__ == "__main__":
    unittest.main()
