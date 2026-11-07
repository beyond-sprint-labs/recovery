"""Read access to invoices. No business rules live here."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.models import InvoiceRow
from app.core.schemas import Invoice


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
