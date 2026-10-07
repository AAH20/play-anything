"""Input and state-isolation contracts for personalization results."""

import unittest

from play_anything.core.personalization_engine import (
    AdaptivePersonalizationEngine,
    BehavioralTelemetry,
    ExpertiseTier,
)


class PersonalizationContracts(unittest.TestCase):
    def setUp(self):
        self.engine = AdaptivePersonalizationEngine()

    def test_identity_and_age_inputs_are_validated(self):
        for user_id in ("", "   ", None):
            with self.subTest(user_id=user_id), self.assertRaisesRegex(ValueError, "user_id"):
                self.engine.calibrate_player_profile(user_id=user_id)
        for age in (-1, True, 18.5, "18"):
            with self.subTest(age=age), self.assertRaisesRegex(ValueError, "stated_age"):
                self.engine.calibrate_player_profile(user_id="player", stated_age=age)

    def test_optional_age_and_default_telemetry_remain_supported(self):
        profile = self.engine.calibrate_player_profile(user_id="player", stated_age=None)
        self.assertEqual(profile.user_id, "player")
        profile_with_defaults = self.engine.calibrate_player_profile(user_id="player", stated_age=38)
        self.assertEqual(profile_with_defaults.user_id, "player")

    def test_telemetry_rejects_nonfinite_negative_and_out_of_range_values(self):
        cases = (
            ("keystroke_cadence_cpm", float("nan")),
            ("hesitation_interval_ms", float("inf")),
            ("error_recovery_latency_ms", -1),
            ("terminal_command_density", 1.01),
            ("cyclomatic_comprehension_score", -0.01),
            ("cyclomatic_comprehension_score", "high"),
        )
        for field, value in cases:
            with self.subTest(field=field, value=value), self.assertRaisesRegex(ValueError, field):
                telemetry = BehavioralTelemetry(**{field: value})
                self.engine.calibrate_player_profile("player", telemetry=telemetry)
        with self.assertRaisesRegex(ValueError, "BehavioralTelemetry"):
            self.engine.calibrate_player_profile("player", telemetry={})

    def test_matchmaking_elo_rejects_noninteger_values(self):
        profile = self.engine.calibrate_player_profile("player", stated_age=38)
        for rating in (True, 2400.5, float("nan"), "2400"):
            with self.subTest(rating=rating), self.assertRaisesRegex(ValueError, "current_elo"):
                self.engine.generate_personalized_suggestions(profile, current_elo=rating)

    def test_leaderboard_snapshots_cannot_mutate_engine_competitors(self):
        first = self.engine.get_division_leaderboard(ExpertiseTier.STAFF_ARCHITECT)
        original_rating = first.champion_spotlight.rating_elo
        first.champion_spotlight.rating_elo = -999
        first.champion_spotlight.life_transformation_facets["physical_vitality"] = "changed"
        first.leaderboard_entries.clear()

        second = self.engine.get_division_leaderboard(ExpertiseTier.STAFF_ARCHITECT)
        self.assertEqual(second.champion_spotlight.rating_elo, original_rating)
        self.assertNotEqual(second.champion_spotlight.life_transformation_facets["physical_vitality"], "changed")
        self.assertTrue(second.leaderboard_entries)

    def test_matchmaking_peers_are_detached_snapshots(self):
        profile = self.engine.calibrate_player_profile("player", stated_age=38)
        first = self.engine.generate_personalized_suggestions(profile, current_elo=2400)
        original = first.human_peers[0].rating_elo
        first.human_peers[0].rating_elo = -999
        first.ai_agent_peers.clear()

        second = self.engine.generate_personalized_suggestions(profile, current_elo=2400)
        self.assertEqual(second.human_peers[0].rating_elo, original)
        self.assertTrue(second.ai_agent_peers)


if __name__ == "__main__":
    unittest.main()
