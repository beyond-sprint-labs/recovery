"""Global contract types, v1.1.

Money and percentages travel as strings so that no float ever touches a monetary
value. All patterns use ``[0-9]`` instead of ``\\d``: ``\\d`` is Unicode-aware and
would accept full-width or Arabic-Indic digits, which ``Decimal`` parses.
"""

import re
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Final, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

# --- monetary and numeric primitives --------------------------------------------------

MONEY_PATTERN: Final = r"^(0|[1-9][0-9]{0,11})\.[0-9]{2}$"
SIGNED_MONEY_PATTERN: Final = r"^-?(0|[1-9][0-9]{0,11})\.[0-9]{2}$"
_PCT_RE: Final = re.compile(r"^(0|[1-9][0-9]{0,2})(\.[0-9]{1,4})?$")

# Non-negative amount: "900.00". No leading zeros, exactly two decimals.
Money = Annotated[str, StringConstraints(strict=True, pattern=MONEY_PATTERN)]

# Signed amount, ONLY for differences such as `merchant_difference_vs_balance` ("-100.00").
SignedMoney = Annotated[str, StringConstraints(strict=True, pattern=SIGNED_MONEY_PATTERN)]


def _validate_pct(value: str) -> str:
    if _PCT_RE.fullmatch(value) is None:
        raise ValueError("pct must be a plain decimal string: no sign, exponent or leading zeros")
    if Decimal(value) > Decimal(100):
        raise ValueError("pct must be between 0 and 100")
    return value


# Percentage per period, "0" to "100", optional decimals ("10", "10.5", "10.50").
Pct = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, max_length=8),
    AfterValidator(_validate_pct),
]

Installments = Annotated[int, Field(strict=True, ge=1, le=120)]


# --- audit trail --------------------------------------------------------------------------


class Severity(StrEnum):
    INFO = "INFO"
    WARN = "WARN"
    CRITICAL = "CRITICAL"


class Actor(BaseModel):
    type: Literal["AGENT", "SYSTEM", "MERCHANT", "CUSTOMER", "PAYPAL"]
    id: str
    mode: str | None = None


class RuleHit(BaseModel):
    code: str
    limit: str | None = None
    attempted: str | None = None
    unit: str | None = None
    message: str | None = None


class AuditEvent(BaseModel):
    event_id: Annotated[str, StringConstraints(pattern=r"^aud_[0-9]{6,}$")]
    seq: Annotated[int, Field(ge=1)]
    ts: datetime
    actor: Actor
    action: str
    invoice_id: str | None
    proposal_id: str | None
    state_from: str | None
    state_to: str | None
    severity: Severity
    rule: RuleHit | None = None
    summary: str
    proposed_by: Actor | None = None
    paypal_called: bool = False
    # Added in v1.1, optional so older consumers keep working.
    source: Literal["API", "UI", "WEBHOOK", "RECONCILIATION"] | None = None
    paypal_ref: str | None = None  # PayPal invoice or draft id affected by the event


# --- requests -----------------------------------------------------------------------------


class CreateProposalIn(BaseModel):
    """Body of ``POST /api/v1/invoices/{id}/proposals``.

    ``extra="forbid"`` makes any unknown field (for example a ``policy`` object) a 422,
    so merchant limits can never be supplied by the caller.
    """

    model_config = ConfigDict(extra="forbid")

    customer_message: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    scenario_id: (
        Annotated[str, StringConstraints(max_length=64, pattern=r"^[A-Za-z0-9_-]+$")] | None
    ) = None


# --- errors -------------------------------------------------------------------------------


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorOut(BaseModel):
    error: ErrorBody