from typing import Protocol

from pydantic import BaseModel, ConfigDict


# Typed error so the RecoveryService can catch it cleanly.
class PayPalError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


class NewInvoiceReq(BaseModel):
    # Strict model for creating invoices. Prevents injections.
    model_config = ConfigDict(extra="forbid")
    invoice_number: str
    amount: str  # Money string
    currency: str = "USD"


class PayPalInvoiceRef(BaseModel):
    id: str
    status: str


class PayPalInvoiceState(BaseModel):
    id: str
    status: str
    amount_due: str | None = None

    # We use Decimal to validate partial payment logic in the mock.
    total_amount: str | None = None


class PayPalGateway(Protocol):
    def create_draft(self, req: NewInvoiceReq) -> PayPalInvoiceRef: ...
    def cancel_invoice(self, paypal_invoice_id: str) -> None: ...
    def send_invoice(self, paypal_invoice_id: str) -> PayPalInvoiceRef: ...
    def delete_draft(self, paypal_invoice_id: str) -> None: ...
    def get_invoice(self, paypal_invoice_id: str) -> PayPalInvoiceState: ...
    def record_payment(self, paypal_invoice_id: str, amount: str) -> None: ...
