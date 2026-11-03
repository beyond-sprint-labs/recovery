import pytest

from app.paypal.mock_gateway import MockPayPalGateway


@pytest.fixture
def gateway():

    # Fixture that initializes a new MockPayPalGateway for each test
    return MockPayPalGateway()


def test_create_and_get_draft(gateway):

    # Test creating a draft and querying it
    ref = gateway.create_draft({"amount": "100.00"}, request_id="req-123")
    assert ref.status == "DRAFT"

    state = gateway.get_invoice(ref.id)
    assert state.status == "DRAFT"
    assert state.amount_due == "100.00"


def test_full_sequence_success(gateway):

    # Test the full flow: create -> cancel original -> send new
    original_ref = gateway.create_draft({"amount": "100.00"}, request_id="req-1")
    draft_ref = gateway.create_draft({"amount": "90.00"}, request_id="req-2")

    gateway.cancel_invoice(original_ref.id)
    assert gateway.get_invoice(original_ref.id).status == "CANCELLED"

    sent_ref = gateway.send_invoice(draft_ref.id)
    assert sent_ref.status == "UNPAID"
    assert gateway.get_invoice(draft_ref.id).status == "UNPAID"


def test_delete_draft(gateway):

    # Test that a draft can be deleted
    ref = gateway.create_draft({"amount": "100.00"}, request_id="req-3")
    gateway.delete_draft(ref.id)

    with pytest.raises(ValueError, match="not found"):
        gateway.get_invoice(ref.id)


def test_forced_failure_on_cancel(gateway):

    # Test simulating a forced failure when cancelling (essential for F1-18)
    original_ref = gateway.create_draft({"amount": "100.00"}, request_id="req-4")
    gateway.fail_next_step = "cancel"

    with pytest.raises(Exception, match="Forced failure at step 'cancel'"):
        gateway.cancel_invoice(original_ref.id)

    # The next attempt should succeed
    gateway.cancel_invoice(original_ref.id)
    assert gateway.get_invoice(original_ref.id).status == "CANCELLED"


def test_record_payment(gateway):

    # Test the payment shortcut (Record Payment)
    ref = gateway.create_draft({"amount": "100.00"}, request_id="req-5")
    gateway.send_invoice(ref.id)
    gateway.record_payment(ref.id, "100.00")

    assert gateway.get_invoice(ref.id).status == "PAID"
