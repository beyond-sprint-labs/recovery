from typing import Protocol, Any
from pydantic import BaseModel


class PayPalInvoiceRef(BaseModel):
    # Reference returned by PayPal when creating or sending an invoice.
    id: str
    status: str


class PayPalInvoiceState(BaseModel):
    # State of an invoice queried from PayPal.
    id: str
    status: str
    amount_due: str | None = None


class PayPalGateway(Protocol):
    # Interface that both the real client and the mock must fulfill

    def create_draft(self, req: dict[str, Any], request_id: str) -> PayPalInvoiceRef:
        """Creates an invoice draft (DRAFT)."""
        ...

    def cancel_invoice(self, paypal_invoice_id: str) -> None:
        """Cancels an existing invoice."""
        ...

    def send_invoice(self, paypal_invoice_id: str) -> PayPalInvoiceRef:
        """Sends an invoice to the customer (changes from DRAFT to UNPAID)."""
        ...

    def delete_draft(self, paypal_invoice_id: str) -> None:
        """Deletes a draft (only works if it is in DRAFT status)"""
        ...

    def get_invoice(self, paypal_invoice_id: str) -> PayPalInvoiceState:
        """Queries the current state of an invoice."""
        ...

    def record_payment(self, paypal_invoice_id: str, amount: str) -> None:
        """Records a manual payment in Sandbox (shortcut for the demo)."""
        ...
