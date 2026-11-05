"""PayPal gateway port (F1-09 / F1-17)."""

from typing import Annotated, Protocol

from pydantic import BaseModel, ConfigDict, EmailStr, StringConstraints

from app.core.schemas import Money

# Error codes raised once the request may already have reached PayPal. After one of these the
# outcome of a mutation is unknown, so callers must re-read the invoice before deciding.
OUTCOME_UNKNOWN_CODES: frozenset[str] = frozenset({"TIMEOUT", "NETWORK_ERROR"})


class PayPalError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")

    @property
    def outcome_unknown(self) -> bool:
        """True when a mutation may or may not have been applied by PayPal."""
        return self.code in OUTCOME_UNKNOWN_CODES


class NewInvoiceReq(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # StringConstraints guarantees the invoice number is never empty
    invoice_number: Annotated[str, StringConstraints(min_length=1)]
    amount: Money
    currency: str = "USD"
    # Customer email from the seed; PAYPAL_SANDBOX_BUYER_EMAIL overrides it in the real gateway
    recipient_email: EmailStr | None = None


class PayPalInvoiceRef(BaseModel):
    id: str
    status: str


class PayPalInvoiceState(BaseModel):
    """Invoice snapshot. A missing amount is None; a missing status is a gateway error."""

    id: str
    status: str
    amount_due: str | None = None
    total_amount: str | None = None
    # None means PayPal reported no payments on the invoice
    paid_amount: str | None = None


class PayPalGateway(Protocol):
    def create_draft(self, req: NewInvoiceReq, request_id: str) -> PayPalInvoiceRef: ...
    def cancel_invoice(self, paypal_invoice_id: str) -> None: ...
    def send_invoice(self, paypal_invoice_id: str) -> PayPalInvoiceRef: ...
    def delete_draft(self, paypal_invoice_id: str) -> None: ...
    def get_invoice(self, paypal_invoice_id: str) -> PayPalInvoiceState: ...
    def record_payment(self, paypal_invoice_id: str, amount: str) -> None: ...
