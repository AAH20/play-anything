"""
Unit tests for Strategic Whales Consortium & AAA Simulation Coordinator.
Uses standard library unittest.
"""

import unittest
from play_anything.core.strategic_whales_consortium import (
    StrategicWhalesCoordinator,
    AAAEnginePlatform,
    SimulationDomain,
    ScaleTier,
    RealWorldEmpowermentCharter
)


class TestStrategicWhales(unittest.TestCase):

    def setUp(self):
        self.coordinator = StrategicWhalesCoordinator()

    def test_unreal_engine_business_warfare_quote(self):
        quote = self.coordinator.generate_bespoke_quote(
            sponsor_organization="Apex Sovereign Fund",
            target_engine=AAAEnginePlatform.UNREAL_ENGINE_5_CHAOS,
            domain=SimulationDomain.BUSINESS_WARFARE,
            scale_tier=ScaleTier.TIER_2_GLOBAL_PUBLISHER,
            target_concurrent_users=250000
        )

        self.assertTrue(quote.quote_id.startswith("whale_"))
        self.assertEqual(quote.sponsor_organization, "Apex Sovereign Fund")
        self.assertEqual(quote.target_engine, AAAEnginePlatform.UNREAL_ENGINE_5_CHAOS)
        self.assertEqual(quote.estimated_timeline_months, 12)
        self.assertIn("$2,000,000", quote.base_contract_bracket_usd)
        self.assertTrue(quote.approved_for_coordination)
        self.assertGreater(len(quote.deliverables), 3)

    def test_surveillance_and_weaponization_sovereign_quote(self):
        quote = self.coordinator.generate_bespoke_quote(
            sponsor_organization="Allied Defense Coalition",
            target_engine=AAAEnginePlatform.HYBRID_SOVEREIGN_MESH,
            domain=SimulationDomain.SURVEILLANCE_AND_WEAPONRY,
            scale_tier=ScaleTier.TIER_3_SOVEREIGN_CONGLOMERATE,
            target_concurrent_users=2000000
        )

        self.assertEqual(quote.scale_tier, ScaleTier.TIER_3_SOVEREIGN_CONGLOMERATE)
        self.assertIn("$8,000,000", quote.base_contract_bracket_usd)
        self.assertEqual(quote.estimated_timeline_months, 18)
        self.assertIn("Cognitive Decision Speed", quote.real_world_impact_kpis[0])

    def test_charter_ethics_invariants(self):
        charter = RealWorldEmpowermentCharter()
        self.assertTrue(charter.enhances_strategic_acumen)
        self.assertTrue(charter.enforces_real_risk_management)
        self.assertTrue(charter.forbids_predatory_escapism)
        self.assertTrue(charter.forbids_sedentary_vr_bubbles)


if __name__ == "__main__":
    unittest.main()
