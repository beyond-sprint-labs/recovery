import pytest

from app.paypal.gateway import NewInvoiceReq, PayPalError
from app.paypal.mock_gateway import MockPayPalGateway


@pytest.fixture
def gateway():
    return MockPayPalGateway()


@pytest.fixture
def sample_req():
    return NewInvoiceReq(invoice_number="INV-001", amount="100.00")


def test_create_draft(gateway, sample_req):
    ref = gateway.create_draft(sample_req)
    assert ref.id.startswith("MOCK-INV-")
    assert ref.status == "DRAFT"


def test_duplicate_invoice_number(gateway, sample_req):
    gateway.create_draft(sample_req)
    with pytest.raises(PayPalError, match="DUPLICATE_INVOICE_NUMBER"):
        gateway.create_draft(sample_req)


def test_full_sequence_success(gateway, sample_req):
    original = gateway.create_draft(sample_req)
    draft_req = NewInvoiceReq(invoice_number="INV-002", amount="90.00")
    draft = gateway.create_draft(draft_req)

    gateway.cancel_invoice(original.id)
    assert gateway.get_invoice(original.id).status == "CANCELLED"

    sent = gateway.send_invoice(draft.id)
    assert sent.status == "UNPAID"
    assert gateway.get_invoice(draft.id).status == "UNPAID"


def test_delete_draft(gateway, sample_req):
    ref = gateway.create_draft(sample_req)
    gateway.delete_draft(ref.id)
    with pytest.raises(PayPalError, match="NOT_FOUND"):
        gateway.get_invoice(ref.id)


def test_forced_failure_on_cancel(gateway, sample_req):
    original = gateway.create_draft(sample_req)
    gateway.fail_steps.add("cancel")

    with pytest.raises(PayPalError, match="SIMULATED_FAILURE"):
        gateway.cancel_invoice(original.id)

    # Next attempt should succeed
    gateway.cancel_invoice(original.id)
    assert gateway.get_invoice(original.id).status == "CANCELLED"


def test_record_partial_and_full_payment(gateway, sample_req):
    ref = gateway.create_draft(sample_req)
    gateway.send_invoice(ref.id)

    gateway.record_payment(ref.id, "30.00")
    assert gateway.get_invoice(ref.id).status == "PARTIALLY_PAID"

    gateway.record_payment(ref.id, "70.00")
    assert gateway.get_invoice(ref.id).status == "PAID"


@pytest.mark.parametrize(
    "invalid_amount",
    [
        "-10.00",  # Negative
        "0.00",  # Zero
        "1e1",  # Scientific notation
        "abc/NaN",  # Not a number
        "100.1",  # Only one decimal
        "",  # Empty string
        "   ",  # Only spaces
    ],
)
def test_record_payment_invalid_amounts(gateway, sample_req, invalid_amount):
    # Regression: invalid amounts must never alter the invoice
    ref = gateway.create_draft(sample_req)
    gateway.send_invoice(ref.id)

    with pytest.raises(PayPalError, match="INVALID_AMOUNT"):
        gateway.record_payment(ref.id, invalid_amount)


def test_record_payment_overpayment(gateway, sample_req):
    ref = gateway.create_draft(sample_req)
    gateway.send_invoice(ref.id)
    with pytest.raises(PayPalError, match="OVERPAYMENT"):
        gateway.record_payment(ref.id, "150.00")


def test_record_payment_on_cancelled_fails(gateway, sample_req):
    ref = gateway.create_draft(sample_req)
    gateway.cancel_invoice(ref.id)
    with pytest.raises(PayPalError, match="INVALID_STATE"):
        gateway.record_payment(ref.id, "100.00")
