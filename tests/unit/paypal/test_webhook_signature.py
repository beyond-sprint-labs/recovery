"""Tests for the PayPalApiWebhookVerifier (F1-19)."""

import pytest
import respx
from httpx import Response

from app.core.config import Settings
from app.paypal.signature import PayPalApiWebhookVerifier

BASE = "https://api-m.sandbox.paypal.com"
TOKEN_URL = f"{BASE}/v1/oauth2/token"
VERIFY_URL = f"{BASE}/v1/notifications/verify-webhook-signature"

HEADERS = {
    "paypal-transmission-id": "trans-123",
    "paypal-transmission-time": "2026-11-08T12:00:00Z",
    "paypal-cert-url": "https://api.paypal.com/v1/notifications/certs/CERT-360caa42-f...",
    "paypal-auth-algo": "SHA256withRSA",
    "paypal-transmission-sig": "sig-abc",
}


@pytest.fixture
def verifier() -> PayPalApiWebhookVerifier:
    settings = Settings(
        paypal_client_id="test_id",
        paypal_client_secret="test_secret",
        paypal_base_url=BASE,
        paypal_webhook_id="wh-test-123",
    )
    return PayPalApiWebhookVerifier(settings)


@respx.mock
def test_verify_returns_true_on_success(verifier):
    respx.post(TOKEN_URL).mock(return_value=Response(200, json={"access_token": "tok"}))
    respx.post(VERIFY_URL).mock(return_value=Response(200, json={"verification_status": "SUCCESS"}))

    body = b'{"id": "WH-123", "event_type": "INVOICING.INVOICE.PAID"}'
    assert verifier.verify(HEADERS, body) is True


@respx.mock
def test_verify_returns_false_on_failure(verifier):
    respx.post(TOKEN_URL).mock(return_value=Response(200, json={"access_token": "tok"}))
    respx.post(VERIFY_URL).mock(return_value=Response(200, json={"verification_status": "FAILURE"}))

    body = b'{"id": "WH-123"}'
    assert verifier.verify(HEADERS, body) is False


def test_verify_returns_false_if_headers_missing(verifier):
    body = b'{"id": "WH-123"}'
    incomplete_headers = {"paypal-transmission-id": "trans-123"}
    assert verifier.verify(incomplete_headers, body) is False
