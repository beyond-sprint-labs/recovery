"""Global contract types, v1.1.

Money and percentages travel as strings so that no float ever touches a monetary
value. All patterns use ``[0-9]`` instead of ``\\d``: ``\\d`` is Unicode-aware and
would accept full-width or Arabic-Indic digits, which ``Decimal`` parses.
"""

import re
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Final, Literal, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from app.core.states import ProposalStatus

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
    state_from: ProposalStatus | None
    state_to: ProposalStatus | None
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


# --- domain models ------------------------------------------------------------------------

Currency = Literal["USD"]


class AlternativeType(StrEnum):
    SETTLEMENT_DISCOUNT = "settlement_discount"
    DOWN_PAYMENT_INSTALLMENTS = "down_payment_installments"


class InvoiceStatus(StrEnum):
    OVERDUE = "OVERDUE"
    PAID = "PAID"
    CANCELLED = "CANCELLED"


class Invoice(BaseModel):
    id: str
    customer_name: str
    currency: Currency
    balance: Money
    due_date: date
    status: InvoiceStatus
    paypal_invoice_id: str | None = None


class Policy(BaseModel):
    """Merchant limits. Read-only for clients: they live on the server (DEC-17)."""

    currency: Currency
    max_discount_pct: Pct
    min_down_payment_pct: Pct
    max_installments: Installments
    max_financing_rate_pct: Pct
    merchant_discount_rate_pct: Pct


class CustomerIntent(BaseModel):
    """What the agent extracts from the customer message. Strict: unknown keys are invalid."""

    model_config = ConfigDict(extra="forbid")

    available_now: Money | None = None
    preferred_installments: Installments | None = None
    requested_discount_pct: Pct | None = None
    desired_date: date | None = None


class SettlementTerms(BaseModel):
    model_config = ConfigDict(extra="forbid")

    discount_pct: Pct


class InstallmentTerms(BaseModel):
    model_config = ConfigDict(extra="forbid")

    down_payment_pct: Pct
    installments: Installments
    periodic_rate_pct: Pct


Terms = SettlementTerms | InstallmentTerms

_TERMS_BY_TYPE: Final = {
    AlternativeType.SETTLEMENT_DISCOUNT: SettlementTerms,
    AlternativeType.DOWN_PAYMENT_INSTALLMENTS: InstallmentTerms,
}


class _TypedTerms(BaseModel):
    """Shared base: ``terms`` must be the shape that ``type`` announces."""

    type: AlternativeType
    terms: Terms

    @model_validator(mode="after")
    def _terms_match_type(self) -> Self:
        if not isinstance(self.terms, _TERMS_BY_TYPE[self.type]):
            raise ValueError(f"terms do not match alternative type {self.type.value}")
        return self


class ScheduleItem(BaseModel):
    n: Annotated[int, Field(ge=0)]
    due_date: date
    amount: Money
    principal: Money
    interest: Money


class Alternative(_TypedTerms):
    amount_due_now: Money
    installment_amount: Money | None = None
    total_paid: Money
    present_value: Money
    financing_cost: Money
    merchant_difference_vs_balance: SignedMoney
    policy_ok: bool
    violations: list[RuleHit] = Field(default_factory=list)
    schedule: list[ScheduleItem]


class AttemptedComputed(BaseModel):
    amount_due_now: Money
    merchant_difference_vs_balance: SignedMoney


class AttemptedAlternative(_TypedTerms):
    """Terms the AI tried that violated policy, kept only as audit evidence."""

    computed: AttemptedComputed


class PolicyCheck(BaseModel):
    status: Literal["PASSED", "BLOCKED"]
    violations: list[RuleHit] = Field(default_factory=list)


class TextNumberCheck(BaseModel):
    status: Literal["PASSED", "FAILED", "SKIPPED"]
    numbers_in_text: list[str] = Field(default_factory=list)
    unmatched: list[str] = Field(default_factory=list)


class PayPalExecution(BaseModel):
    new_invoice_id: str | None = None
    original_invoice_id: str | None = None
    steps: list[str] = Field(default_factory=list)


class ProposalOut(BaseModel):
    """Merchant-side view of a proposal. BLOCKED is a business result: HTTP 200."""

    proposal_id: str
    invoice_id: str
    status: ProposalStatus
    engine_version: str
    currency: Currency
    customer_intent: CustomerIntent
    alternatives: list[Alternative]
    attempted: list[AttemptedAlternative] = Field(default_factory=list)
    blocked_reasons: list[RuleHit] = Field(default_factory=list)
    explanation: str | None = None
    customer_message_draft: str | None = None
    policy_check: PolicyCheck
    text_number_check: TextNumberCheck
    paypal_called: bool
    # Optional additions so GET /proposals/{id} can serve the execution screen.
    approved_alternative: AlternativeType | None = None
    paypal: PayPalExecution | None = None
    audit_event: AuditEvent | None = None

    @model_validator(mode="after")
    def _blocked_iff_reasons(self) -> Self:
        is_blocked = self.status is ProposalStatus.BLOCKED
        if is_blocked != bool(self.blocked_reasons):
            raise ValueError("blocked_reasons must be present if and only if status is BLOCKED")
        return self


# --- customer-facing view: one alternative, nothing internal ---------------------------------


class CustomerAlternativeView(_TypedTerms):
    model_config = ConfigDict(extra="forbid")

    amount_due_now: Money
    installment_amount: Money | None = None
    total_paid: Money
    schedule: list[ScheduleItem]


class CustomerProposalView(BaseModel):
    """What the customer sees. ``extra="forbid"`` so internal fields can never leak in."""

    model_config = ConfigDict(extra="forbid")

    proposal_id: str
    invoice_id: str
    currency: Currency
    original_balance: Money
    alternative: CustomerAlternativeView
    customer_message: str
    expires_at: datetime
    status: ProposalStatus
    simulation_notice: str


# --- merchant / customer action bodies and responses ------------------------------------


class ApproveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alternative_type: AlternativeType
    note: Annotated[str, StringConstraints(max_length=200)] | None = None


class RejectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: Annotated[str, StringConstraints(max_length=200)] | None = None


class RespondIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["ACCEPT", "DECLINE"]


class ApproveOut(BaseModel):
    proposal_id: str
    status: ProposalStatus
    approved_alternative: AlternativeType
    customer_link: str
    customer_token_expires_at: datetime
    audit_events: list[AuditEvent]


class RespondOut(BaseModel):
    proposal_id: str
    status: ProposalStatus
    paypal: PayPalExecution | None = None
    audit_events: list[AuditEvent]


class ProposalStatusOut(BaseModel):
    """Shared by reject, reconcile and sandbox record-payment."""

    proposal_id: str
    status: ProposalStatus
    audit_events: list[AuditEvent]


class AuditEventsPage(BaseModel):
    items: list[AuditEvent]
    next_seq: Annotated[int, Field(ge=0)]


# --- errors -------------------------------------------------------------------------------


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorOut(BaseModel):
    error: ErrorBody
