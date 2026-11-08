"""Map an approved alternative to the PayPal replacement invoice (F1-18b).

Pure functions: no database and no network. The replacement invoice is what PayPal will bill,
so every figure comes from the persisted engine result and never from a request (DEC-03).
Both alternatives are invoiced for ``amount_due_now``:

* ``settlement_discount``: the discounted balance, paid in full.
* ``down_payment_installments``: only the down payment is invoiced. Its payment moves the
  proposal to PAID, shown as "First scheduled payment confirmed" (DEC-29). The remaining
  installments are NOT billed by PayPal in Phase 1 and must be labelled as simulated.
"""

import re
from collections.abc import Sequence
from decimal import Decimal
from typing import Final

from pydantic import ValidationError

from app.core.schemas import Alternative, AlternativeType, Money
from app.paypal.gateway import NewInvoiceReq

INVOICE_NUMBER_PREFIX: Final = "REC-"
# PayPal Invoicing v2 limits ``detail.invoice_number`` to 25 characters.
MAX_INVOICE_NUMBER_LENGTH: Final = 25
_INVOICE_NUMBER_RE: Final = re.compile(r"[A-Za-z0-9_-]+")

FIRST_PAYMENT_LABEL: Final = "First scheduled payment confirmed"
FULL_PAYMENT_LABEL: Final = "Payment confirmed"
INSTALLMENTS_SIMULATION_NOTICE: Final = (
    "Only the down payment is invoiced in PayPal Sandbox; the remaining installments are simulated."
)


class AlternativeMappingError(ValueError):
    """The approved alternative cannot be turned into a safe PayPal invoice request."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def replacement_invoice_number(proposal_id: str) -> str:
    """Deterministic and unique per proposal: PayPal rejects duplicates (DUPLICATE_INVOICE_NUMBER).

    Retries of the same proposal reuse the same number, so a second draft can never be created.
    """
    number = f"{INVOICE_NUMBER_PREFIX}{proposal_id}"
    if len(number) > MAX_INVOICE_NUMBER_LENGTH or _INVOICE_NUMBER_RE.fullmatch(number) is None:
        raise AlternativeMappingError(
            "INVALID_INVOICE_NUMBER",
            f"Invoice number must be 1-{MAX_INVOICE_NUMBER_LENGTH} characters of A-Z, a-z, 0-9, "
            "'_' or '-'",
        )
    return number


def select_approved_alternative(
    alternatives: Sequence[Alternative], approved: AlternativeType | None
) -> Alternative:
    """Return the merchant-approved alternative; it must exist and be inside policy."""
    if approved is None:
        raise AlternativeMappingError(
            "NO_APPROVED_ALTERNATIVE", "The proposal has no approved alternative"
        )
    for alternative in alternatives:
        if alternative.type is approved:
            if not alternative.policy_ok:
                raise AlternativeMappingError(
                    "ALTERNATIVE_NOT_OFFERED", "The approved alternative violates the policy"
                )
            return alternative
    raise AlternativeMappingError(
        "ALTERNATIVE_NOT_OFFERED", "The approved alternative is not part of the proposal"
    )


def replacement_amount(alternative: Alternative) -> Money:
    """Amount to invoice in PayPal, cross-checked against the engine's own schedule."""
    amount = Decimal(alternative.amount_due_now)
    if amount <= Decimal("0"):
        raise AlternativeMappingError(
            "NON_POSITIVE_AMOUNT", "The amount to invoice must be greater than zero"
        )
    if not alternative.schedule or Decimal(alternative.schedule[0].amount) != amount:
        raise AlternativeMappingError(
            "SCHEDULE_MISMATCH", "The first scheduled payment differs from the amount due now"
        )
    if (
        alternative.type is AlternativeType.SETTLEMENT_DISCOUNT
        and Decimal(alternative.total_paid) != amount
    ):
        raise AlternativeMappingError(
            "SETTLEMENT_TOTAL_MISMATCH", "A settlement must be paid in a single payment"
        )
    return alternative.amount_due_now


def build_replacement_request(
    *, proposal_id: str, alternative: Alternative, recipient_email: str
) -> NewInvoiceReq:
    """Build the deterministic request for ``PayPalGateway.create_draft``."""
    number = replacement_invoice_number(proposal_id)
    amount = replacement_amount(alternative)
    try:
        return NewInvoiceReq(invoice_number=number, amount=amount, recipient_email=recipient_email)
    except ValidationError as err:
        raise AlternativeMappingError(
            "INVALID_REPLACEMENT_REQUEST", "The replacement invoice request is invalid"
        ) from err


def confirmation_label(alternative_type: AlternativeType) -> str:
    """UI and audit wording for the payment that moves a proposal to PAID."""
    if alternative_type is AlternativeType.DOWN_PAYMENT_INSTALLMENTS:
        return FIRST_PAYMENT_LABEL
    return FULL_PAYMENT_LABEL


def simulation_notice(alternative_type: AlternativeType) -> str | None:
    """Disclosure required by F1-18 when part of an alternative is simulated."""
    if alternative_type is AlternativeType.DOWN_PAYMENT_INSTALLMENTS:
        return INSTALLMENTS_SIMULATION_NOTICE
    return None
