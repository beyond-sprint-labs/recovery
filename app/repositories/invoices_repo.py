"""Read access to invoices. No business rules live here."""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.models import CustomerRow, InvoiceRow
from app.core.schemas import Invoice


@dataclass(frozen=True, slots=True, kw_only=True)
class PaymentContext:
    """Server-side data needed to replace an invoice in PayPal. Never exposed over HTTP."""

    paypal_invoice_id: str | None
    recipient_email: str


def _to_schema(row: InvoiceRow) -> Invoice:
    # ``customer_id`` is deliberately not exposed: Invoice is the public contract.
    return Invoice.model_validate(
        {
            "id": row.id,
            "customer_name": row.customer_name,
            "currency": row.currency,
            "balance": row.balance,
            "due_date": date.fromisoformat(row.due_date),
            "status": row.status,
            "paypal_invoice_id": row.paypal_invoice_id,
        }
    )


class InvoicesRepo:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, invoice_id: str) -> Invoice | None:
        row = self._session.get(InvoiceRow, invoice_id)
        return _to_schema(row) if row is not None else None

    def list_all(self) -> list[Invoice]:
        rows = self._session.scalars(select(InvoiceRow).order_by(InvoiceRow.id)).all()
        return [_to_schema(row) for row in rows]

    def get_payment_context(self, invoice_id: str) -> PaymentContext | None:
        """PayPal id of the original invoice and the customer's email (server-side only)."""
        stmt = (
            select(InvoiceRow.paypal_invoice_id, CustomerRow.email)
            .join(CustomerRow, CustomerRow.id == InvoiceRow.customer_id)
            .where(InvoiceRow.id == invoice_id)
        )
        row = self._session.execute(stmt).one_or_none()
        if row is None:
            return None
        return PaymentContext(paypal_invoice_id=row.paypal_invoice_id, recipient_email=row.email)
