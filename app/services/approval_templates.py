"""Deterministic customer-facing approval messages (DEC-28).

The final message shown to the customer is rendered from fixed templates (see
``docs/marketing/microcopy_en.md``) using only figures produced by the finance engine. No LLM
is involved. The allow-list handed to ``text_guard`` is deliberately narrower than the one
used for drafts: it contains exactly the figures the templates can print.
"""

from decimal import Decimal
from typing import Final

from app.core.schemas import Alternative, AlternativeType, InstallmentTerms, SettlementTerms
from app.services.text_guard import AllowedNumbers

SETTLEMENT_TEMPLATE: Final = (
    "Hello, your proposed settlement terms for invoice {invoice_id} have been approved. "
    "You can settle the full balance today with a single payment of ${amount_due_now} "
    "({discount_pct}% discount). Please review the terms and confirm below."
)

INSTALLMENTS_TEMPLATE: Final = (
    "Hello, your proposed installment arrangement for invoice {invoice_id} has been approved: "
    "pay ${amount_due_now} today, followed by {installments} monthly payments of "
    "${installment_amount}, for a total of ${total_paid}. "
    "Please review the schedule and confirm below."
)


def render_customer_message(*, invoice_id: str, alternative: Alternative) -> str:
    """Render the single-option message for the approved alternative.

    Raises ``ValueError`` when the alternative does not carry the figures its template needs,
    so an inconsistent alternative can never produce a partial message.
    """
    terms = alternative.terms
    if alternative.type is AlternativeType.SETTLEMENT_DISCOUNT:
        if not isinstance(terms, SettlementTerms):
            raise ValueError("settlement alternative carries the wrong terms")
        return SETTLEMENT_TEMPLATE.format(
            invoice_id=invoice_id,
            amount_due_now=alternative.amount_due_now,
            discount_pct=terms.discount_pct,
        )
    if alternative.type is AlternativeType.DOWN_PAYMENT_INSTALLMENTS:
        if not isinstance(terms, InstallmentTerms) or alternative.installment_amount is None:
            raise ValueError("installment alternative is missing required figures")
        return INSTALLMENTS_TEMPLATE.format(
            invoice_id=invoice_id,
            amount_due_now=alternative.amount_due_now,
            installments=terms.installments,
            installment_amount=alternative.installment_amount,
            total_paid=alternative.total_paid,
        )
    raise ValueError("unsupported alternative type")


def build_final_message_allowed_numbers(
    *, alternative: Alternative, invoice_id: str
) -> AllowedNumbers:
    """Exactly the figures the approval templates may print, and nothing else."""
    terms = alternative.terms
    values: set[Decimal] = {
        Decimal(alternative.amount_due_now),
        Decimal(alternative.total_paid),
    }
    if alternative.installment_amount is not None:
        values.add(Decimal(alternative.installment_amount))
    if isinstance(terms, SettlementTerms):
        values.add(Decimal(terms.discount_pct))
    else:
        values.add(Decimal(terms.installments))
    return AllowedNumbers(values=frozenset(values), invoice_ids=frozenset({invoice_id}))
