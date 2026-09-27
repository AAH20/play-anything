"""
Unit tests for Adaptive Personalization Engine & Behavioral Calibration.
Uses standard library unittest.
"""

import unittest
from play_anything.core.personalization_engine import (
    AdaptivePersonalizationEngine,
    BehavioralTelemetry,
    AgeCluster,
    ExpertiseTier,
    OnboardingCalibrationGate
)


class TestPersonalizationEngine(unittest.TestCase):

    def setUp(self):
        self.engine = AdaptivePersonalizationEngine()
        self.gate = OnboardingCalibrationGate(
            map_id="map_auth_01",
            map_title="Apollo Auth Fortress"
        )

    def test_kid_youth_profile_calibration(self):
        profile = self.engine.calibrate_player_profile(
            user_id="user_cadet_12",
            stated_age=12
        )
        self.assertEqual(profile.age_cluster, AgeCluster.YOUTH_CADET)
        self.assertEqual(profile.expertise_tier, ExpertiseTier.INITIATE)
        self.assertFalse(profile.skip_basic_tutorials)
        self.assertEqual(profile.scaffolding_style, "visual_story_metaphor")

        onboarding = self.engine.adapt_map_onboarding(self.gate, profile)
        self.assertEqual(onboarding["track"], "YOUTH_CADET_DISCOVERY_TRACK")
        self.assertIn("Cadet", onboarding["banner_title"])

    def test_pro_architect_fast_track_calibration(self):
        profile = self.engine.calibrate_player_profile(
            user_id="user_architect_38",
            stated_age=38,
            telemetry=BehavioralTelemetry(
                keystroke_cadence_cpm=350.0,
                terminal_command_density=0.92,
                cyclomatic_comprehension_score=0.96
            )
        )
        self.assertEqual(profile.age_cluster, AgeCluster.PRO_ARCHITECT)
        self.assertEqual(profile.expertise_tier, ExpertiseTier.STAFF_ARCHITECT)
        self.assertTrue(profile.skip_basic_tutorials)
        self.assertEqual(profile.scaffolding_style, "raw_ast_telemetry")

        onboarding = self.engine.adapt_map_onboarding(self.gate, profile)
        self.assertEqual(onboarding["track"], "EXECUTIVE_PRO_FAST_TRACK")
        self.assertEqual(onboarding["onboarding_time_seconds"], 15)
        self.assertIn("Direct Git Diff", onboarding["actions"][0])

    def test_senior_sage_cognitive_vitality_calibration(self):
        profile = self.engine.calibrate_player_profile(
            user_id="user_sage_68",
            stated_age=68
        )
        self.assertEqual(profile.age_cluster, AgeCluster.SENIOR_SAGE)
        self.assertTrue(profile.high_contrast_mode)
        self.assertEqual(profile.ui_font_scale, 1.25)
        self.assertGreater(profile.countdown_timer_multiplier, 1.0)

        onboarding = self.engine.adapt_map_onboarding(self.gate, profile)
        self.assertEqual(onboarding["track"], "COGNITIVE_VITALITY_SAGE_TRACK")
        self.assertIn("Paced Cognitive", onboarding["banner_title"])

    def test_zero_shot_behavioral_inference_without_stated_age(self):
        # Fast CLI pro telemetry
        telemetry_pro = BehavioralTelemetry(
            keystroke_cadence_cpm=320.0,
            terminal_command_density=0.88,
            hesitation_interval_ms=90.0
        )
        profile_pro = self.engine.calibrate_player_profile(
            user_id="user_anon_pro",
            telemetry=telemetry_pro
        )
        self.assertEqual(profile_pro.age_cluster, AgeCluster.PRO_ARCHITECT)
        self.assertTrue(profile_pro.skip_basic_tutorials)


if __name__ == "__main__":
    unittest.main()
