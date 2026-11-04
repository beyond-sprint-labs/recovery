"""Known roots, bounds and controlled failures for monthly rate bisection."""

import unittest
from decimal import Decimal, localcontext

from app.finance.engine import (
    FinanceCalculationError,
    FinanceValidationError,
    evaluate_cash_flows,
)


class RateSolverTests(unittest.TestCase):
    def test_original_notebook_flows_and_out_of_range_case(self):
        result = evaluate_cash_flows(
            [Decimal("-10000")] + [Decimal("1000")] * 11 + [Decimal("950")]
        )
        self.assertGreater(result.monthly_rate, 0)
        self.assertLess(result.monthly_rate, Decimal("0.1"))
        with self.assertRaises(FinanceCalculationError):
            evaluate_cash_flows([Decimal("-10000")] + [Decimal("1000")] * 5 + [Decimal("950")])

    def test_known_rate_and_annual_conversions(self):
        result = evaluate_cash_flows([Decimal("-100"), Decimal("110")])
        self.assertEqual(result.monthly_rate, Decimal("0.10000000"))
        self.assertEqual(result.annual_nominal_rate, Decimal("1.20000000"))
        self.assertEqual(result.effective_annual_rate, Decimal("2.1384"))

    def test_inclusive_endpoints_and_rate_above_contract_input_limit(self):
        for payment, expected in (("100", "0"), ("300", "2"), ("250", "1.5")):
            with self.subTest(payment=payment):
                result = evaluate_cash_flows([Decimal("-100"), Decimal(payment)])
                self.assertEqual(result.monthly_rate, Decimal(expected))

    def test_equidistant_flows_with_a_zero_payment(self):
        result = evaluate_cash_flows([Decimal("-100"), Decimal("0"), Decimal("121")])
        self.assertEqual(result.monthly_rate, Decimal("0.10000000"))

    def test_golden_cash_flows_have_small_residual_after_rate_rounding(self):
        flows = [Decimal(value) for value in ("-700", "240.37", "240.37", "240.36")]
        result = evaluate_cash_flows(flows)
        with localcontext() as context:
            context.prec = 40
            pv = sum(
                (flow / (1 + result.monthly_rate) ** t for t, flow in enumerate(flows[1:], 1)),
                Decimal("0"),
            )
            self.assertLess(abs(pv - Decimal("700")), Decimal("0.01"))
        # Rounded installments need not imply exactly the original 1.5% rate.
        self.assertLess(abs(result.monthly_rate - Decimal("0.015")), Decimal("0.00001"))

    def test_out_of_range_and_nonconvergence_are_controlled_errors(self):
        for payment in ("90", "301"):
            with self.subTest(payment=payment), self.assertRaises(FinanceCalculationError):
                evaluate_cash_flows([Decimal("-100"), Decimal(payment)])
        with self.assertRaises(FinanceCalculationError):
            evaluate_cash_flows([Decimal("-100"), Decimal("110")], max_iterations=1)

    def test_example_converges_with_21_bisections_and_four_output_places(self):
        result = evaluate_cash_flows([Decimal("-1000")] + [Decimal("100")] * 12, max_iterations=21)
        self.assertEqual(result.monthly_rate, Decimal("0.0292"))
        self.assertEqual(result.annual_nominal_rate, Decimal("0.3507"))
        self.assertEqual(result.effective_annual_rate, Decimal("0.4130"))
        for value in (
            result.monthly_rate,
            result.annual_nominal_rate,
            result.effective_annual_rate,
        ):
            self.assertEqual(value.as_tuple().exponent, -4)

    def test_half_up_boundary(self):
        result = evaluate_cash_flows([Decimal("-100"), Decimal("112.34565")])
        self.assertEqual(result.monthly_rate, Decimal("0.1235"))

    def test_invalid_inputs(self):
        for flows in (
            [],
            [Decimal("-100")],
            [Decimal("100"), Decimal("110")],
            [Decimal("-100"), Decimal("0")],
            [Decimal("-100"), Decimal("NaN")],
            [Decimal("-100"), Decimal("-10"), Decimal("120")],
            [-100.0, 110.0],
        ):
            with self.subTest(flows=flows), self.assertRaises(FinanceValidationError):
                evaluate_cash_flows(flows)
        with self.assertRaises(FinanceValidationError):
            evaluate_cash_flows([Decimal("-100"), Decimal("110")], max_iterations=True)


if __name__ == "__main__":
    unittest.main()
