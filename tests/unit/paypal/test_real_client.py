import json

import httpx
import pytest
import respx
from httpx import Response

from app.core.config import Settings
from app.paypal.client import RealPayPalGateway
from app.paypal.factory import build_gateway
from app.paypal.gateway import NewInvoiceReq, PayPalError
from app.paypal.mock_gateway import MockPayPalGateway

BASE = "https://api-m.sandbox.paypal.com"
TOKEN_URL = f"{BASE}/v1/oauth2/token"
INVOICES_URL = f"{BASE}/v2/invoicing/invoices"


def make_settings(**overrides: object) -> Settings:
    """Deterministic settings: never reads the developer's .env file."""
    values: dict[str, object] = {
        "paypal_client_id": "test_id",
        "paypal_client_secret": "test_secret",
        "paypal_base_url": BASE,
        "paypal_merchant_email": "merchant@example.com",
        "paypal_sandbox_buyer_email": None,
        "allow_sandbox_payment_shortcut": True,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def token_route(expires_in: int = 3600) -> respx.Route:
    return respx.post(TOKEN_URL).mock(
        return_value=Response(200, json={"access_token": "tok", "expires_in": expires_in})
    )


@pytest.fixture
def gateway() -> RealPayPalGateway:
    return RealPayPalGateway(make_settings())


@pytest.fixture
def req() -> NewInvoiceReq:
    return NewInvoiceReq(
        invoice_number="INV-TEST-001", amount="100.00", recipient_email="seed@example.com"
    )


# ---------------------------------------------------------------- create_draft


@respx.mock
def test_create_draft_parses_full_representation(gateway, req):
    token_route()
    route = respx.post(INVOICES_URL).mock(
        return_value=Response(
            201,
            json={
                "id": "INV2-REAL-123",
                "status": "DRAFT",
                "links": [{"href": f"{INVOICES_URL}/INV2-REAL-123", "rel": "self"}],
            },
        )
    )

    ref = gateway.create_draft(req, "req-1")

    assert (ref.id, ref.status) == ("INV2-REAL-123", "DRAFT")
    payload = json.loads(route.calls.last.request.content)
    assert payload["invoicer"]["email_address"] == "merchant@example.com"
    assert payload["primary_recipients"][0]["billing_info"]["email_address"] == "seed@example.com"
    assert payload["detail"]["invoice_number"] == "INV-TEST-001"
    assert payload["items"][0]["unit_amount"] == {"currency_code": "USD", "value": "100.00"}
    assert "req-1" not in route.calls.last.request.content.decode()


@respx.mock
def test_create_draft_parses_bare_link_response(gateway, req):
    token_route()
    respx.post(INVOICES_URL).mock(
        return_value=Response(
            201, json={"rel": "self", "href": f"{INVOICES_URL}/INV2-LINK-9", "method": "GET"}
        )
    )

    ref = gateway.create_draft(req, "req-1")

    assert (ref.id, ref.status) == ("INV2-LINK-9", "DRAFT")


@respx.mock
def test_create_draft_sandbox_buyer_email_overrides_seed(req):
    gateway = RealPayPalGateway(make_settings(paypal_sandbox_buyer_email="sandbox@example.com"))
    token_route()
    route = respx.post(INVOICES_URL).mock(return_value=Response(201, json={"id": "INV2-1"}))

    gateway.create_draft(req, "req-1")

    payload = json.loads(route.calls.last.request.content)
    assert (
        payload["primary_recipients"][0]["billing_info"]["email_address"] == "sandbox@example.com"
    )


@respx.mock
def test_create_draft_without_any_recipient_fails_before_http(gateway):
    bare = NewInvoiceReq(invoice_number="INV-TEST-002", amount="100.00")

    with pytest.raises(PayPalError) as exc:
        gateway.create_draft(bare, "req-1")

    assert exc.value.code == "CONFIG_ERROR"


@respx.mock
def test_create_draft_duplicate_number_exposes_issue_as_code(gateway, req):
    token_route()
    respx.post(INVOICES_URL).mock(
        return_value=Response(
            422,
            json={
                "name": "UNPROCESSABLE_ENTITY",
                "message": "The requested action could not be performed",
                "details": [{"issue": "DUPLICATE_INVOICE_NUMBER"}],
            },
        )
    )

    with pytest.raises(PayPalError) as exc:
        gateway.create_draft(req, "req-1")

    assert exc.value.code == "DUPLICATE_INVOICE_NUMBER"
    assert exc.value.outcome_unknown is False


# ---------------------------------------------------------------- OAuth handling


@respx.mock
def test_token_is_cached_between_calls(gateway):
    token = token_route()
    respx.get(f"{INVOICES_URL}/INV2-1").mock(
        return_value=Response(200, json={"id": "INV2-1", "status": "SENT"})
    )

    gateway.get_invoice("INV2-1")
    gateway.get_invoice("INV2-1")

    assert token.call_count == 1


@respx.mock
def test_expired_token_is_refreshed(gateway):
    token = token_route()
    respx.get(f"{INVOICES_URL}/INV2-1").mock(
        return_value=Response(200, json={"id": "INV2-1", "status": "SENT"})
    )

    gateway.get_invoice("INV2-1")
    gateway._token_expires_at = 0.0
    gateway.get_invoice("INV2-1")

    assert token.call_count == 2


@respx.mock
def test_http_401_triggers_exactly_one_reauthentication(gateway):
    token = token_route()
    route = respx.get(f"{INVOICES_URL}/INV2-1").mock(
        side_effect=[Response(401), Response(200, json={"id": "INV2-1", "status": "SENT"})]
    )

    state = gateway.get_invoice("INV2-1")

    assert state.status == "SENT"
    assert token.call_count == 2
    assert route.call_count == 2


@respx.mock
def test_persistent_401_is_not_retried_forever(gateway):
    token = token_route()
    route = respx.get(f"{INVOICES_URL}/INV2-1").mock(side_effect=[Response(401), Response(401)])

    with pytest.raises(PayPalError) as exc:
        gateway.get_invoice("INV2-1")

    assert exc.value.code == "PAYPAL_HTTP_401"
    assert token.call_count == 2
    assert route.call_count == 2


@respx.mock
def test_auth_failure_does_not_leak_secrets(gateway):
    respx.post(TOKEN_URL).mock(return_value=Response(401, text="bad test_secret"))

    with pytest.raises(PayPalError) as exc:
        gateway.get_invoice("INV2-1")

    assert exc.value.code == "AUTH_FAILED"
    assert "test_secret" not in str(exc.value)


# ---------------------------------------------------------------- error translation


@respx.mock
def test_server_error_5xx_is_outcome_unknown(gateway):
    token_route()
    respx.post(f"{INVOICES_URL}/INV2-1/cancel").mock(
        return_value=Response(
            503,
            json={"name": "SERVICE_UNAVAILABLE", "message": "PayPal is down", "debug_id": "abc123"},
        )
    )

    with pytest.raises(PayPalError) as exc:
        gateway.cancel_invoice("INV2-1")

    assert exc.value.code == "PAYPAL_HTTP_503"
    # Critical: a 503 on a mutation means the outcome is unknown
    assert exc.value.outcome_unknown is True


@respx.mock
def test_read_timeout_is_outcome_unknown(gateway):
    token_route()
    respx.post(f"{INVOICES_URL}/INV2-1/cancel").mock(side_effect=httpx.ReadTimeout("slow"))

    with pytest.raises(PayPalError) as exc:
        gateway.cancel_invoice("INV2-1")

    assert exc.value.code == "TIMEOUT"
    assert exc.value.outcome_unknown is True


@respx.mock
def test_connection_error_is_outcome_unknown(gateway):
    token_route()
    respx.post(f"{INVOICES_URL}/INV2-1/send").mock(side_effect=httpx.ConnectError("down"))

    with pytest.raises(PayPalError) as exc:
        gateway.send_invoice("INV2-1")

    assert exc.value.code == "NETWORK_ERROR"
    assert exc.value.outcome_unknown is True


# ---------------------------------------------------------------- invoice operations


@respx.mock
def test_get_invoice_reads_amounts_and_payments(gateway):
    token_route()
    respx.get(f"{INVOICES_URL}/INV2-1").mock(
        return_value=Response(
            200,
            json={
                "id": "INV2-1",
                "status": "PARTIALLY_PAID",
                "amount": {"currency_code": "USD", "value": "100.00"},
                "due_amount": {"currency_code": "USD", "value": "70.00"},
                "payments": {"paid_amount": {"currency_code": "USD", "value": "30.00"}},
            },
        )
    )

    state = gateway.get_invoice("INV2-1")

    assert state.status == "PARTIALLY_PAID"
    assert (state.total_amount, state.amount_due, state.paid_amount) == (
        "100.00",
        "70.00",
        "30.00",
    )


@respx.mock
def test_get_invoice_without_status_fails_closed(gateway):
    token_route()
    respx.get(f"{INVOICES_URL}/INV2-1").mock(return_value=Response(200, json={"id": "INV2-1"}))

    with pytest.raises(PayPalError) as exc:
        gateway.get_invoice("INV2-1")

    assert exc.value.code == "INVALID_RESPONSE"


@respx.mock
def test_get_invoice_missing_amounts_are_none_not_invented(gateway):
    token_route()
    respx.get(f"{INVOICES_URL}/INV2-1").mock(
        return_value=Response(200, json={"id": "INV2-1", "status": "DRAFT"})
    )

    state = gateway.get_invoice("INV2-1")

    assert (state.amount_due, state.total_amount, state.paid_amount) == (None, None, None)


@respx.mock
def test_cancel_send_and_delete_hit_the_expected_endpoints(gateway):
    token_route()
    cancel = respx.post(f"{INVOICES_URL}/INV2-1/cancel").mock(return_value=Response(204))
    send = respx.post(f"{INVOICES_URL}/INV2-2/send").mock(return_value=Response(200, json={}))
    delete = respx.delete(f"{INVOICES_URL}/INV2-3").mock(return_value=Response(204))

    gateway.cancel_invoice("INV2-1")
    ref = gateway.send_invoice("INV2-2")
    gateway.delete_draft("INV2-3")

    assert (cancel.call_count, send.call_count, delete.call_count) == (1, 1, 1)
    assert (ref.id, ref.status) == ("INV2-2", "SENT")


# ---------------------------------------------------------------- record_payment


@respx.mock
def test_record_payment_sends_method_field(gateway):
    token_route()
    route = respx.post(f"{INVOICES_URL}/INV2-1/payments").mock(
        return_value=Response(200, json={"payment_id": "PAY-1"})
    )

    gateway.record_payment("INV2-1", "300.00")

    payload = json.loads(route.calls.last.request.content)
    assert payload["method"] == "OTHER"
    assert "payment_method" not in payload
    assert payload["amount"] == {"currency_code": "USD", "value": "300.00"}


@respx.mock
def test_record_payment_blocked_when_shortcut_disabled():
    gateway = RealPayPalGateway(make_settings(allow_sandbox_payment_shortcut=False))

    with pytest.raises(PayPalError) as exc:
        gateway.record_payment("INV2-1", "300.00")

    assert exc.value.code == "SANDBOX_ONLY"


@respx.mock
def test_record_payment_blocked_outside_sandbox():
    gateway = RealPayPalGateway(make_settings(paypal_base_url="https://api-m.paypal.com"))

    with pytest.raises(PayPalError) as exc:
        gateway.record_payment("INV2-1", "300.00")

    assert exc.value.code == "SANDBOX_ONLY"


@pytest.mark.parametrize("bad_amount", ["1e1", "0.00", "-5.00", "300.0", ""])
@respx.mock
def test_record_payment_rejects_invalid_amounts_before_http(gateway, bad_amount):
    with pytest.raises(PayPalError) as exc:
        gateway.record_payment("INV2-1", bad_amount)

    assert exc.value.code == "INVALID_AMOUNT"


# ---------------------------------------------------------------- wiring


def test_constructor_requires_credentials_and_merchant_email():
    with pytest.raises(PayPalError) as exc:
        RealPayPalGateway(make_settings(paypal_client_id=""))

    assert exc.value.code == "CONFIG_ERROR"
    assert "PAYPAL_CLIENT_ID" in exc.value.message


def test_build_gateway_selects_by_mode_only():
    real = build_gateway(make_settings(demo_mode=False, paypal_mode="real"))
    mock = build_gateway(make_settings(demo_mode=False, paypal_mode="mock"))

    assert isinstance(real, RealPayPalGateway)
    assert isinstance(mock, MockPayPalGateway)
