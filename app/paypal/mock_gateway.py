import uuid
from decimal import Decimal
from typing import Any

from pydantic import TypeAdapter, ValidationError

from app.core.schemas import Money

from .gateway import NewInvoiceReq, PayPalError, PayPalGateway, PayPalInvoiceRef, PayPalInvoiceState

# TypeAdapter validates Annotated types (such as Money) outside of a model
MONEY_ADAPTER = TypeAdapter(Money)


class MockPayPalGateway(PayPalGateway):
    def __init__(self):
        self.invoices_db: dict[str, dict[str, Any]] = {}
        self.fail_steps: set[str] = set()

    def _check_failure(self, step: str):
        if step in self.fail_steps:
            self.fail_steps.remove(step)
            raise PayPalError("SIMULATED_FAILURE", f"Forced failure at step '{step}'")

    def create_draft(self, req: NewInvoiceReq) -> PayPalInvoiceRef:
        self._check_failure("create")
        for inv in self.invoices_db.values():
            if inv["req"].invoice_number == req.invoice_number:
                raise PayPalError(
                    "DUPLICATE_INVOICE_NUMBER",
                    f"Invoice {req.invoice_number} already exists.",
                )
        mock_id = f"MOCK-INV-{uuid.uuid4().hex[:8].upper()}"
        self.invoices_db[mock_id] = {
            "id": mock_id,
            "status": "DRAFT",
            "req": req,
            "paid_amount": Decimal("0.00"),
        }
        return PayPalInvoiceRef(id=mock_id, status="DRAFT")

    def cancel_invoice(self, paypal_invoice_id: str) -> None:
        self._check_failure("cancel")
        invoice = self._get_or_fail(paypal_invoice_id)
        if invoice["status"] in ["PAID", "CANCELLED"]:
            raise PayPalError(
                "INVALID_STATE",
                f"Cannot cancel invoice in status {invoice['status']}",
            )
        invoice["status"] = "CANCELLED"

    def send_invoice(self, paypal_invoice_id: str) -> PayPalInvoiceRef:
        self._check_failure("send")
        invoice = self._get_or_fail(paypal_invoice_id)
        if invoice["status"] != "DRAFT":
            raise PayPalError(
                "INVALID_STATE",
                f"Can only send DRAFT invoices. Current: {invoice['status']}",
            )
        invoice["status"] = "UNPAID"
        return PayPalInvoiceRef(id=paypal_invoice_id, status="UNPAID")

    def delete_draft(self, paypal_invoice_id: str) -> None:
        self._check_failure("delete")
        invoice = self._get_or_fail(paypal_invoice_id)
        if invoice["status"] != "DRAFT":
            raise PayPalError("INVALID_STATE", "Only DRAFT invoices can be deleted")
        del self.invoices_db[paypal_invoice_id]

    def get_invoice(self, paypal_invoice_id: str) -> PayPalInvoiceState:
        invoice = self._get_or_fail(paypal_invoice_id)
        return PayPalInvoiceState(
            id=invoice["id"],
            status=invoice["status"],
            amount_due=str(Decimal(invoice["req"].amount) - invoice["paid_amount"]),
            total_amount=invoice["req"].amount,
        )

    def record_payment(self, paypal_invoice_id: str, amount: str) -> None:
        invoice = self._get_or_fail(paypal_invoice_id)

        if invoice["status"] not in ["UNPAID", "PARTIALLY_PAID"]:
            raise PayPalError(
                "INVALID_STATE",
                f"Cannot record payment for invoice in status {invoice['status']}",
            )

        # Strict validation with the shared Money type
        try:
            validated_amount = MONEY_ADAPTER.validate_python(amount)
            payment = Decimal(validated_amount)
        except (ValidationError, ValueError) as err:
            raise PayPalError(
                "INVALID_AMOUNT",
                "Amount must be a valid non-negative Money string (e.g., '100.00')",
            ) from err

        if payment <= Decimal("0.00"):
            raise PayPalError("INVALID_AMOUNT", "Payment amount must be greater than zero")

        total = Decimal(invoice["req"].amount)
        new_paid = invoice["paid_amount"] + payment

        if new_paid > total:
            raise PayPalError("OVERPAYMENT", "Payment amount exceeds total invoice amount")

        invoice["paid_amount"] = new_paid
        invoice["status"] = "PAID" if new_paid == total else "PARTIALLY_PAID"

    def _get_or_fail(self, paypal_invoice_id: str) -> dict:
        if paypal_invoice_id not in self.invoices_db:
            raise PayPalError("NOT_FOUND", f"Invoice {paypal_invoice_id} not found")
        return self.invoices_db[paypal_invoice_id]
