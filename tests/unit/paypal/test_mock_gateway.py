import pytest

from app.paypal.gateway import NewInvoiceReq, PayPalError
from app.paypal.mock_gateway import MockPayPalGateway

REQUEST_ID = "req-test-1"


@pytest.fixture
def gateway():
    return MockPayPalGateway()


@pytest.fixture
def sample_req():
    return NewInvoiceReq(invoice_number="INV-001", amount="100.00")


def test_create_draft(gateway, sample_req):
    ref = gateway.create_draft(sample_req, REQUEST_ID)
    assert ref.id.startswith("MOCK-INV-")
    assert ref.status == "DRAFT"


def test_duplicate_invoice_number(gateway, sample_req):
    gateway.create_draft(sample_req, REQUEST_ID)
    with pytest.raises(PayPalError, match="DUPLICATE_INVOICE_NUMBER"):
        gateway.create_draft(sample_req, REQUEST_ID)


def test_full_sequence_success(gateway, sample_req):
    original = gateway.create_draft(sample_req, REQUEST_ID)
    gateway.send_invoice(original.id)
    draft_req = NewInvoiceReq(invoice_number="INV-002", amount="90.00")
    draft = gateway.create_draft(draft_req, "req-test-2")

    gateway.cancel_invoice(original.id)
    assert gateway.get_invoice(original.id).status == "CANCELLED"

    sent = gateway.send_invoice(draft.id)
    assert sent.status == "SENT"
    assert gateway.get_invoice(draft.id).status == "SENT"


def test_delete_draft(gateway, sample_req):
    ref = gateway.create_draft(sample_req, REQUEST_ID)
    gateway.delete_draft(ref.id)
    with pytest.raises(PayPalError, match="NOT_FOUND"):
        gateway.get_invoice(ref.id)


def test_forced_failure_on_cancel(gateway, sample_req):
    original = gateway.create_draft(sample_req, REQUEST_ID)
    gateway.send_invoice(original.id)
    gateway.fail_steps.add("cancel")

    with pytest.raises(PayPalError, match="SIMULATED_FAILURE"):
        gateway.cancel_invoice(original.id)

    # Next attempt should succeed
    gateway.cancel_invoice(original.id)
    assert gateway.get_invoice(original.id).status == "CANCELLED"


def test_record_partial_and_full_payment(gateway, sample_req):
    ref = gateway.create_draft(sample_req, REQUEST_ID)
    gateway.send_invoice(ref.id)

    gateway.record_payment(ref.id, "30.00")
    state = gateway.get_invoice(ref.id)
    assert state.status == "PARTIALLY_PAID"
    assert state.paid_amount == "30.00"

    gateway.record_payment(ref.id, "70.00")
    assert gateway.get_invoice(ref.id).status == "PAID"


@pytest.mark.parametrize("paid_amount", ["30.00", "100.00"])
def test_cancel_invoice_with_payments_is_rejected(gateway, sample_req, paid_amount):
    # Evidence: PayPal answers 422 CANNOT_CANCEL_PAID_INVOICE (spike F1-03)
    ref = gateway.create_draft(sample_req, REQUEST_ID)
    gateway.send_invoice(ref.id)
    gateway.record_payment(ref.id, paid_amount)

    with pytest.raises(PayPalError, match="CANNOT_CANCEL_PAID_INVOICE"):
        gateway.cancel_invoice(ref.id)


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
    ref = gateway.create_draft(sample_req, REQUEST_ID)
    gateway.send_invoice(ref.id)

    with pytest.raises(PayPalError, match="INVALID_AMOUNT"):
        gateway.record_payment(ref.id, invalid_amount)


def test_record_payment_overpayment(gateway, sample_req):
    ref = gateway.create_draft(sample_req, REQUEST_ID)
    gateway.send_invoice(ref.id)
    with pytest.raises(PayPalError, match="OVERPAYMENT"):
        gateway.record_payment(ref.id, "150.00")


def test_record_payment_on_cancelled_fails(gateway, sample_req):
    ref = gateway.create_draft(sample_req, REQUEST_ID)
    gateway.cancel_invoice(ref.id)
    with pytest.raises(PayPalError, match="INVALID_STATE"):
        gateway.record_payment(ref.id, "100.00")
