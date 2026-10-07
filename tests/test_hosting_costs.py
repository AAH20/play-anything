import unittest
from play_anything.core.hosting_costs import estimate_hosting
from play_anything.core.venture_planner import calculate_plan


class HostingTests(unittest.TestCase):
    def test_free_business_cloudflare_with_supabase(self):
        h=estimate_hosting(dict(web='cloudflare_free',database='free'))
        self.assertEqual(h['monthly'],0)
        self.assertTrue(h['eligible'])

    def test_hobby_is_not_commercial(self):
        self.assertFalse(estimate_hosting(dict(web='vercel_hobby'))['eligible'])
        self.assertTrue(estimate_hosting(dict(web='vercel_hobby',commercial=False))['eligible'])

    def test_free_excess_does_not_invent_a_paid_overage(self):
        h=estimate_hosting(dict(database='free',db_gb=2))
        self.assertEqual(h['monthly'],0)
        self.assertFalse(h['eligible'])
        self.assertIn('upgrade required',h['warnings'][0])

    def test_paid_rates_and_credits(self):
        h=estimate_hosting(dict(web='vercel_pro',seats=2,vercel_usage=32,database='pro',db_gb=10,egress_gb=300))
        self.assertAlmostEqual(h['monthly'],40+12+25+.25+4.5)
        w=estimate_hosting(dict(web='cloudflare_workers',requests=12000000,cpu_ms=5))
        self.assertAlmostEqual(w['monthly'],5+.6+.6)

    def test_hosting_is_counted_once(self):
        before=calculate_plan(['world'])
        after=calculate_plan(['world'],hosting=dict(web='vercel_pro',database='pro'))
        self.assertEqual(after['total_monthly']-before['total_monthly'],45)
        self.assertEqual(before['profit']-after['profit'],45)
        self.assertEqual(before['contribution'],after['contribution'])

    def test_output_labels_rates_as_illustrative_not_live_verified(self):
        estimate=estimate_hosting()
        self.assertEqual(estimate['estimate_type'],'illustrative')
        self.assertFalse(estimate['price_verified'])
        self.assertIsNone(estimate['verified_on'])
        self.assertIn('not a quote',estimate['estimate_basis'].lower())

    def test_invalid_usage(self):
        for setting in ({'mau':-1},{'mau':1.2},{'extra':'NaN'},{'web':'fake'},{'seats':0},{'commercial':'yes'}):
            with self.assertRaises(ValueError): estimate_hosting(setting)
