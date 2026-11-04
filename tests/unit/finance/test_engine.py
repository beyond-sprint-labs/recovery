"""Financial results, rounding and policy checks against frozen examples."""

import json
import unittest
from decimal import Decimal
from pathlib import Path

from app.finance.engine import (
    FinanceCalculationError,
    FinanceValidationError,
    build_alternative,
    build_alternatives,
    calculate_present_value,
)

EXAMPLES = Path(__file__).resolve().parents[3] / "contracts" / "examples"


class FinancialEngineTests(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads((EXAMPLES / "policy.json").read_text(encoding="utf-8"))
        self.terms = {"down_payment_pct": "30", "installments": 3, "periodic_rate_pct": "1.5"}

    def build(self, *, terms=None, policy=None, balance="1000.00"):
        return build_alternative(
            balance=balance,
            alternative_type="down_payment_installments",
            terms=self.terms if terms is None else terms,
            policy=self.policy if policy is None else policy,
            pivot_date="2026-11-11",
        )

    def test_00_complete_golden_alternatives_match_frozen_contract(self):
        result = build_alternatives(
            balance="1000.00",
            policy=self.policy,
            pivot_date="2026-11-11",
            settlement_terms={"discount_pct": "10"},
            installment_terms=self.terms,
        )
        expected = json.loads((EXAMPLES / "proposal_pending.json").read_text(encoding="utf-8"))
        self.assertEqual(result, expected["alternatives"])
        # Results are directly JSON serializable, including all dates and amounts.
        self.assertEqual(json.loads(json.dumps(result, allow_nan=False)), result)

    def test_pv_rounds_once_and_uses_merchant_rate(self):
        self.assertEqual(
            calculate_present_value([Decimal("0")] + [Decimal("0.01")] * 3, "20"),
            Decimal("0.02"),
        )
        result = self.build(policy=self.policy | {"merchant_discount_rate_pct": "0"})
        self.assertEqual(result["present_value"], result["total_paid"])
        self.assertEqual(result["installment_amount"], "240.37")

    def test_down_payment_and_discount_half_up(self):
        result = self.build(
            balance="0.05",
            terms=self.terms
            | {
                "down_payment_pct": "10",
                "installments": 1,
                "periodic_rate_pct": "0",
            },
        )
        self.assertEqual(result["amount_due_now"], "0.01")
        self.assertEqual(result["schedule"][1]["amount"], "0.04")
        settlement = build_alternative(
            balance="0.05",
            alternative_type="settlement_discount",
            terms={"discount_pct": "10"},
            policy=self.policy,
            pivot_date="2026-11-11",
        )
        self.assertEqual(settlement["amount_due_now"], "0.04")

    def test_all_installment_policy_violations_without_rounding_rates(self):
        result = self.build(
            terms={
                "down_payment_pct": "19.9999",
                "installments": 7,
                "periodic_rate_pct": "2.0001",
            }
        )
        self.assertFalse(result["policy_ok"])
        self.assertEqual(
            {hit["code"] for hit in result["violations"]},
            {
                "MIN_DOWN_PAYMENT_PCT",
                "MAX_INSTALLMENTS",
                "MAX_FINANCING_RATE_PCT",
            },
        )
        rate_hit = next(
            hit for hit in result["violations"] if hit["code"] == "MAX_FINANCING_RATE_PCT"
        )
        self.assertEqual(rate_hit["attempted"], "2.0001")

    def test_blocked_settlement_matches_contract_evidence(self):
        result = build_alternative(
            balance="1000.00",
            alternative_type="settlement_discount",
            terms={"discount_pct": "40"},
            policy=self.policy,
            pivot_date="2026-11-11",
        )
        self.assertFalse(result["policy_ok"])
        self.assertEqual(result["violations"][0]["code"], "MAX_DISCOUNT_PCT")
        self.assertEqual(result["amount_due_now"], "600.00")
        self.assertEqual(result["merchant_difference_vs_balance"], "-400.00")

    def test_zero_rate_full_down_payment_zero_balance_and_120_installments(self):
        for balance, down, count in (
            ("1000.00", "100", 3),
            ("0.00", "30", 3),
            ("1000.00", "0", 120),
        ):
            with self.subTest(balance=balance, down=down, count=count):
                result = self.build(
                    balance=balance,
                    terms={
                        "down_payment_pct": down,
                        "installments": count,
                        "periodic_rate_pct": "0",
                    },
                )
                self.assertEqual(result["total_paid"], balance)
                self.assertEqual(result["financing_cost"], "0.00")
                self.assertEqual(len(result["schedule"]), count + 1)
                self.assertEqual(
                    sum(Decimal(row["principal"]) for row in result["schedule"]), Decimal(balance)
                )

    def test_invalid_terms_policy_currency_and_input_formats(self):
        for terms in (
            self.terms | {"extra": "value"},
            {"discount_pct": "10"},
            self.terms | {"periodic_rate_pct": 1.5},
            self.terms | {"installments": True},
            self.terms | {"down_payment_pct": "150"},
        ):
            with self.subTest(terms=terms), self.assertRaises(FinanceValidationError):
                self.build(terms=terms)
        for policy in (self.policy | {"currency": "MXN"}, {}, self.policy | {"extra": 1}):
            with self.subTest(policy=policy), self.assertRaises(FinanceValidationError):
                self.build(policy=policy)
        with self.assertRaises(FinanceValidationError):
            self.build(balance=1000.0)
        with self.assertRaises(FinanceValidationError):
            calculate_present_value([Decimal("NaN")], "1")

    def test_total_overflow_is_a_controlled_error(self):
        with self.assertRaises(FinanceCalculationError):
            self.build(
                balance="999999999999.99",
                terms={
                    "down_payment_pct": "0",
                    "installments": 1,
                    "periodic_rate_pct": "100",
                },
            )


if __name__ == "__main__":
    unittest.main()
