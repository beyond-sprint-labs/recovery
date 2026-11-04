"""Boundary tests; mocked math checks integration, not financial formulas."""

import json
import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from app.finance import engine as finance
from app.finance import schedule


class FinanceScaffoldTests(unittest.TestCase):
    def test_original_notebook_monthly_schedule_and_json(self):
        # Original example: 900 at nominal annual 30%, now explicitly monthly 2.5%.
        result = schedule.build_dated_schedule("900.00", "2.5", 12, "2027-01-31")
        self.assertEqual(len(result), 12)
        self.assertEqual(result[0]["due_date"], "2027-02-28")
        self.assertEqual(result[-1]["due_date"], "2028-01-31")
        self.assertEqual(sum(Decimal(row["principal"]) for row in result), Decimal("900"))
        self.assertTrue(
            all(
                Decimal(row["amount"]) == Decimal(row["principal"]) + Decimal(row["interest"])
                for row in result
            )
        )
        self.assertEqual(json.loads(json.dumps(result, allow_nan=False)), result)
        recovered = finance.evaluate_cash_flows(
            [Decimal("-900")] + [Decimal(row["amount"]) for row in result]
        )
        self.assertEqual(recovered.monthly_rate, Decimal("0.0250"))

    def test_original_notebook_date_anchors(self):
        for pivot, expected in (
            ("2027-01-31", ["2027-01-31", "2027-02-28", "2027-03-31", "2027-04-30"]),
            ("2028-01-31", ["2028-01-31", "2028-02-29", "2028-03-31", "2028-04-30"]),
            ("2027-01-30", ["2027-01-30", "2027-02-28", "2027-03-30", "2027-04-30"]),
            ("2027-01-15", ["2027-01-15", "2027-02-15", "2027-03-15", "2027-04-15"]),
            ("2027-02-28", ["2027-02-28", "2027-03-31", "2027-04-30", "2027-05-31"]),
        ):
            with self.subTest(pivot=pivot):
                self.assertEqual(
                    [d.isoformat() for d in schedule.monthly_due_dates(pivot, 3)], expected
                )

    def test_00_golden_schedule(self):
        # Actual amortization test, not a mock. PV is outside this helper.
        result = schedule.build_dated_schedule("700.00", "1.5", 3, "2028-01-31")
        self.assertEqual([row["amount"] for row in result], ["240.37", "240.37", "240.36"])
        self.assertEqual([row["interest"] for row in result], ["10.50", "7.05", "3.55"])
        self.assertEqual(
            Decimal("300.00") + sum((Decimal(row["amount"]) for row in result), Decimal(0)),
            Decimal("1021.10"),
        )

    def test_policy_rate_comparison_does_not_round(self):
        self.assertFalse(finance.financing_rate_within_policy("1.5001", "1.5"))
        self.assertTrue(finance.financing_rate_within_policy("1.5000", "1.5"))
        self.assertTrue(finance.financing_rate_within_policy("0", "0"))
        with self.assertRaises(finance.FinanceValidationError):
            finance.financing_rate_within_policy("100.0001", "100")

    def test_contract_input_preserves_rate_precision(self):
        request = schedule.validate_variables(
            principal="100.00",
            periodic_rate_pct="2.1234",
            n=120,
            pivot_date="2028-01-31",
        )
        self.assertEqual(request.periodic_rate_pct, "2.1234")
        self.assertEqual(request.pivot_date, date(2028, 1, 31))

    def test_invalid_contract_inputs(self):
        valid = dict(principal="100.00", periodic_rate_pct="2", n=12, pivot_date="2028-01-31")
        for field, value in (
            ("principal", 100.0),
            ("principal", "-1.00"),
            ("principal", "0100.00"),
            ("periodic_rate_pct", "100.0001"),
            ("periodic_rate_pct", 2.0),
            ("n", True),
            ("n", "12"),
            ("n", 121),
            ("pivot_date", "2028-02-30"),
            ("pivot_date", 1234567890),
        ):
            with (
                self.subTest(field=field, value=value),
                self.assertRaises(finance.FinanceValidationError),
            ):
                schedule.validate_variables(**(valid | {field: value}))

    def test_month_end_and_original_anchor(self):
        self.assertEqual(
            schedule.monthly_due_dates("2028-01-31", 3),
            [date(2028, 1, 31), date(2028, 2, 29), date(2028, 3, 31), date(2028, 4, 30)],
        )
        self.assertEqual(schedule.monthly_due_dates("2028-01-30", 2)[-1], date(2028, 3, 30))
        with self.assertRaises(finance.FinanceValidationError):
            schedule.monthly_due_dates("9999-12-31", 1)

    def test_serialization_and_half_up(self):
        self.assertEqual(finance.format_money(Decimal("240.365")), "240.37")
        self.assertEqual(finance.format_money(Decimal("-0.001"), signed=True), "0.00")
        self.assertEqual(finance.format_money(Decimal("-1.00"), signed=True), "-1.00")
        for value in (
            1.0,
            Decimal("NaN"),
            Decimal("Infinity"),
            Decimal("-0.001"),
            Decimal("1000000000000.00"),
        ):
            with self.subTest(value=value), self.assertRaises(finance.FinanceCalculationError):
                finance.format_money(value)

    def test_zero_rate_solver_and_invalid_float_input(self):
        self.assertEqual(
            finance.evaluate_cash_flows([Decimal("-100"), Decimal("100")]).monthly_rate,
            Decimal("0"),
        )
        with self.assertRaises(finance.FinanceValidationError):
            finance.evaluate_cash_flows([-100.0, 100.0])

    def test_zero_rate_and_last_payment_residue(self):
        rows = finance.build_mthly_schedule(Decimal("100"), Decimal("0"), 3)
        self.assertEqual(
            [row.amount for row in rows], [Decimal("33.33"), Decimal("33.33"), Decimal("33.34")]
        )
        self.assertTrue(all(row.interest == 0 for row in rows))

    def test_single_payment_zero_principal_and_contract_extremes(self):
        rows = finance.build_mthly_schedule(Decimal("100"), Decimal("0.015"), 1)
        self.assertEqual(
            rows[0], finance.PaymentAmounts(Decimal("101.50"), Decimal("100"), Decimal("1.50"))
        )
        for principal, rate in (("0", "1"), ("1000", "1"), ("1000", "0.000001")):
            rows = finance.build_mthly_schedule(Decimal(principal), Decimal(rate), 120)
            self.assertEqual(len(rows), 120)
            self.assertEqual(sum(row.principal for row in rows), Decimal(principal))
            self.assertTrue(all(row.amount == row.principal + row.interest for row in rows))

    def test_direct_math_input_validation(self):
        for principal, rate, count in (
            (100.0, Decimal("0"), 3),
            (Decimal("100"), 0.01, 3),
            (Decimal("NaN"), Decimal("0"), 3),
            (Decimal("100"), Decimal("1.01"), 3),
            (Decimal("100.001"), Decimal("0"), 3),
            (Decimal("100"), Decimal("0"), True),
        ):
            with (
                self.subTest(principal=principal, rate=rate, count=count),
                self.assertRaises(finance.FinanceValidationError),
            ):
                finance.build_mthly_schedule(principal, rate, count)

    def test_impossible_fixed_cent_payment_is_rejected(self):
        with self.assertRaises(finance.FinanceCalculationError):
            finance.build_mthly_schedule(Decimal("0.02"), Decimal("0"), 4)

    def test_wrapper_converts_rate_and_returns_contract_models(self):
        row = finance.PaymentAmounts(Decimal("102.00"), Decimal("100.00"), Decimal("2.00"))
        with patch.object(schedule, "build_mthly_schedule", return_value=[row]) as hook:
            result = schedule.build_dated_schedule("100.00", "2.1234", 1, "2028-01-31")
        hook.assert_called_once_with(Decimal("100.00"), Decimal("0.021234"), 1)
        self.assertEqual(
            result[0],
            {
                "n": 1,
                "due_date": "2028-02-29",
                "amount": "102.00",
                "principal": "100.00",
                "interest": "2.00",
            },
        )

    def test_invalid_math_output_is_rejected(self):
        for rows in (
            [],
            [finance.PaymentAmounts(Decimal("100"), Decimal("99"), Decimal("0"))],
            [finance.PaymentAmounts(Decimal("99"), Decimal("99"), Decimal("0"))],
            [finance.PaymentAmounts(Decimal("100.001"), Decimal("100"), Decimal("0.001"))],
        ):
            with (
                self.subTest(rows=rows),
                patch.object(schedule, "build_mthly_schedule", return_value=rows),
                self.assertRaises(finance.FinanceCalculationError),
            ):
                schedule.build_dated_schedule("100.00", "0", 1, "2028-01-31")


if __name__ == "__main__":
    unittest.main()
