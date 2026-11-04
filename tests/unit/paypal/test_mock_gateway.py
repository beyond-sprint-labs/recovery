import pytest

from app.paypal.gateway import NewInvoiceReq, PayPalError
from app.paypal.mock_gateway import MockPayPalGateway


@pytest.fixture
def gateway():
    return MockPayPalGateway()


@pytest.fixture
def sample_req():
    return NewInvoiceReq(invoice_number="INV-001", amount="100.00")


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


def test_multi_step_forced_failure(gateway, sample_req):
    # We test that it fails on cancel and then on delete (for the rollback)
    original = gateway.create_draft(sample_req)
    draft_req = NewInvoiceReq(invoice_number="INV-003", amount="90.00")
    draft = gateway.create_draft(draft_req)

    gateway.fail_steps = {"cancel", "delete"}

    with pytest.raises(PayPalError):
        gateway.cancel_invoice(original.id)

    with pytest.raises(PayPalError):
        gateway.delete_draft(draft.id)


def test_record_partial_and_full_payment(gateway, sample_req):
    ref = gateway.create_draft(sample_req)
    gateway.send_invoice(ref.id)

    # partial payment
    gateway.record_payment(ref.id, "30.00")
    assert gateway.get_invoice(ref.id).status == "PARTIALLY_PAID"

    # total payment
    gateway.record_payment(ref.id, "70.00")
    assert gateway.get_invoice(ref.id).status == "PAID"


def test_record_payment_on_cancelled_fails(gateway, sample_req):
    ref = gateway.create_draft(sample_req)
    gateway.cancel_invoice(ref.id)
    with pytest.raises(PayPalError, match="INVALID_STATE"):
        gateway.record_payment(ref.id, "100.00")
