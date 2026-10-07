import json
import math
import unittest
from decimal import Inexact, ROUND_DOWN, localcontext

from play_anything.core.venture_planner import calculate_plan


class VenturePlannerNumericBoundaryTests(unittest.TestCase):
    def test_tiny_positive_price_keeps_finite_serializable_outputs(self):
        result = calculate_plan([], assumptions={"price": "1e-30"})

        self.assertTrue(math.isfinite(result["margin_pct"]))
        self.assertTrue(math.isfinite(result["profit"]))
        json.dumps(result, allow_nan=False)

    def test_break_even_integer_respects_json_digit_limit(self):
        assumptions = {
            "price": "1e-4300",
            "transaction_fee": 0,
            "platform_pct": 0,
            "payment_pct": 0,
            "refund_pct": 0,
            "acquisition": 0,
            "new_customers": 0,
            "maintenance": 0,
            "overhead": 1,
            "hourly": 0,
        }
        overrides = {"world": {"fixed": 0, "variable": 0, "hours": 0}}

        with self.assertRaisesRegex(ValueError, "break_even_payers.*digit limit"):
            calculate_plan([], assumptions=assumptions, overrides=overrides)

        assumptions["price"] = "1e-4299"
        result = calculate_plan([], assumptions=assumptions, overrides=overrides)
        self.assertEqual(result["break_even_payers"], 10**4299)
        json.dumps(result, allow_nan=False)

    def test_ratio_beyond_finite_float_range_is_a_controlled_error(self):
        with self.assertRaisesRegex(ValueError, "margin_pct.*finite numeric output range"):
            calculate_plan([], assumptions={"price": "1e-320"})

        assumptions = {
            "price": "1e-320",
            "transaction_fee": 0,
            "platform_pct": 0,
            "payment_pct": 0,
            "refund_pct": 0,
            "acquisition": 0,
            "new_customers": 0,
            "maintenance": 0,
            "overhead": 0,
            "hourly": 50,
        }
        overrides = {"world": {"fixed": 0, "variable": 0, "hours": 8}}
        with self.assertRaisesRegex(ValueError, "setup_payback_months.*finite numeric output range"):
            calculate_plan([], assumptions=assumptions, overrides=overrides)

    def test_large_supported_inputs_still_return_finite_json(self):
        assumptions = {
            "active": 10**9,
            "paying": 10**9,
            "price": 10**9,
            "hourly": 10**9,
            "maintenance": 10**9,
            "overhead": 10**9,
            "acquisition": 10**9,
            "new_customers": 10**9,
            "platform_pct": 100,
            "payment_pct": 100,
            "transaction_fee": 10**9,
            "refund_pct": 100,
            "input_tokens": 10**9,
            "output_tokens": 10**9,
            "input_rate": 10**9,
            "output_rate": 10**9,
        }
        result = calculate_plan(["enterprise"], assumptions=assumptions)

        self.assertTrue(math.isfinite(result["profit"]))
        json.dumps(result, allow_nan=False)

    def test_nonzero_gross_underflow_is_rejected_but_exact_zero_is_supported(self):
        zero_price = calculate_plan([], assumptions={"price": 0})
        self.assertEqual(zero_price["gross"], 0)
        self.assertIsNone(zero_price["margin_pct"])

        with self.assertRaisesRegex(ValueError, "underflow"):
            calculate_plan([], assumptions={"price": "1e-999999998"})

    def test_plan_is_independent_of_callers_decimal_context(self):
        assumptions = {
            "active": 100,
            "paying": 10,
            "price": 20,
            "hourly": 10,
            "maintenance": 2,
            "overhead": 15,
            "acquisition": 10,
            "new_customers": 2,
            "platform_pct": 5,
            "payment_pct": 3,
            "transaction_fee": 0.5,
            "refund_pct": 2,
        }
        expected = calculate_plan([], assumptions)
        with localcontext() as context:
            context.prec = 2
            context.rounding = ROUND_DOWN
            context.Emin = -10
            context.Emax = 10
            context.traps[Inexact] = True
            actual = calculate_plan([], assumptions)
            self.assertEqual(context.prec, 2)
            self.assertEqual(context.rounding, ROUND_DOWN)
            self.assertEqual(context.Emin, -10)
            self.assertTrue(context.traps[Inexact])
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
