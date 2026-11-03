import uuid
from typing import Any, Literal
from .gateway import PayPalGateway, PayPalInvoiceRef, PayPalInvoiceState


class MockPayPalGateway(PayPalGateway):
    def __init__(self):

        # In-memory dictionary to simulate the PayPal database.
        self.invoices_db: dict[str, dict[str, Any]] = {}

        # Allows forcing a failure on the next step (for testing).
        self.fail_next_step: Literal["create", "cancel", "send", "delete"] | None = None

    def _check_failure(self, step: str):

        # Checks if we need to simulate an error at this step.
        if self.fail_next_step == step:
            self.fail_next_step = None  # Resets for the next attempt
            raise Exception(f"Mock PayPal Error: Forced failure at step '{step}'")

    def create_draft(self, req: dict[str, Any], request_id: str) -> PayPalInvoiceRef:
        self._check_failure("create")

        # We simulate a PayPal ID (e.g. MOCK-INV-A1B2C3D4).
        mock_id = f"MOCK-INV-{uuid.uuid4().hex[:8].upper()}"
        self.invoices_db[mock_id] = {
            "id": mock_id,
            "status": "DRAFT",
            "request_id": request_id,
            "req": req,
        }
        return PayPalInvoiceRef(id=mock_id, status="DRAFT")

    def cancel_invoice(self, paypal_invoice_id: str) -> None:
        self._check_failure("cancel")

        if paypal_invoice_id not in self.invoices_db:
            raise ValueError(f"Invoice {paypal_invoice_id} not found")

        invoice = self.invoices_db[paypal_invoice_id]
        if invoice["status"] in ["PAID", "CANCELLED"]:
            raise ValueError(f"Cannot cancel invoice in status {invoice['status']}")

        invoice["status"] = "CANCELLED"

    def send_invoice(self, paypal_invoice_id: str) -> PayPalInvoiceRef:
        self._check_failure("send")

        if paypal_invoice_id not in self.invoices_db:
            raise ValueError(f"Invoice {paypal_invoice_id} not found")

        invoice = self.invoices_db[paypal_invoice_id]
        if invoice["status"] != "DRAFT":
            raise ValueError(
                f"Can only send DRAFT invoices. Current status: {invoice['status']}"
            )

        invoice["status"] = "UNPAID"
        return PayPalInvoiceRef(id=paypal_invoice_id, status="UNPAID")

    def delete_draft(self, paypal_invoice_id: str) -> None:
        self._check_failure("delete")

        if paypal_invoice_id not in self.invoices_db:
            raise ValueError(f"Invoice {paypal_invoice_id} not found")

        invoice = self.invoices_db[paypal_invoice_id]
        if invoice["status"] != "DRAFT":
            raise ValueError("Only DRAFT invoices can be deleted")

        del self.invoices_db[paypal_invoice_id]

    def get_invoice(self, paypal_invoice_id: str) -> PayPalInvoiceState:
        if paypal_invoice_id not in self.invoices_db:
            raise ValueError(f"Invoice {paypal_invoice_id} not found")

        invoice = self.invoices_db[paypal_invoice_id]
        return PayPalInvoiceState(
            id=invoice["id"],
            status=invoice["status"],
            amount_due=invoice["req"].get("amount", "0.00"),
        )

    def record_payment(self, paypal_invoice_id: str, amount: str) -> None:
        if paypal_invoice_id not in self.invoices_db:
            raise ValueError(f"Invoice {paypal_invoice_id} not found")

        invoice = self.invoices_db[paypal_invoice_id]
        invoice["status"] = "PAID"
