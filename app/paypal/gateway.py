from typing import Annotated, Protocol

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.core.schemas import Money


class PayPalError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


class NewInvoiceReq(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # We use StringConstraints to make sure a string isnt empty
    invoice_number: Annotated[str, StringConstraints(min_length=1)]
    amount: Money
    currency: str = "USD"


class PayPalInvoiceRef(BaseModel):
    id: str
    status: str


class PayPalInvoiceState(BaseModel):
    id: str
    status: str
    amount_due: str | None = None
    total_amount: str | None = None


class PayPalGateway(Protocol):
    def create_draft(self, req: NewInvoiceReq) -> PayPalInvoiceRef: ...
    def cancel_invoice(self, paypal_invoice_id: str) -> None: ...
    def send_invoice(self, paypal_invoice_id: str) -> PayPalInvoiceRef: ...
    def delete_draft(self, paypal_invoice_id: str) -> None: ...
    def get_invoice(self, paypal_invoice_id: str) -> PayPalInvoiceState: ...
    def record_payment(self, paypal_invoice_id: str, amount: str) -> None: ...
