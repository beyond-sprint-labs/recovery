"""Validate generated results against the project's actual shared schemas."""

import json
from pathlib import Path

from app.core.schemas import Alternative, Policy
from app.finance.engine import build_alternatives


def test_generated_alternatives_validate_against_shared_schemas():
    examples = Path(__file__).resolve().parents[3] / "contracts" / "examples"
    policy = Policy.model_validate_json((examples / "policy.json").read_text(encoding="utf-8"))
    result = build_alternatives(
        balance="1000.00",
        pivot_date="2026-11-11",
        policy=policy.model_dump(),
        settlement_terms={"discount_pct": "10"},
        installment_terms={"down_payment_pct": "30", "installments": 3, "periodic_rate_pct": "1.5"},
    )
    for alternative in result:
        assert Alternative.model_validate(alternative).model_dump(mode="json") == alternative
    expected = json.loads((examples / "proposal_pending.json").read_text(encoding="utf-8"))
    assert result == expected["alternatives"]
