"""Webhook signature verification (F1-19 / DEC-24)."""

from collections.abc import Mapping
from typing import Protocol

import httpx

from app.core.config import Settings


class WebhookVerifier(Protocol):
    def verify(self, headers: Mapping[str, str], raw_body: bytes) -> bool: ...


class MockWebhookVerifier:
    """Accepts every payload. Valid only when PAYPAL_MODE=mock."""

    def verify(self, headers: Mapping[str, str], raw_body: bytes) -> bool:
        return True


class PayPalApiWebhookVerifier:
    """Calls the official PayPal endpoint to verify the signature (DEC-24).

    This avoids downloading the cert_url (SSRF risk) and relies on PayPal's own infrastructure.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base_url = str(settings.paypal_base_url).rstrip("/")

    def verify(self, headers: Mapping[str, str], raw_body: bytes) -> bool:
        # These are the mandatory headers sent by PayPal
        required = {
            "paypal-transmission-id",
            "paypal-transmission-time",
            "paypal-cert-url",
            "paypal-auth-algo",
            "paypal-transmission-sig",
        }
        # Case-insensitive check
        normalized = {k.lower(): v for k, v in headers.items()}
        if not required.issubset(normalized.keys()):
            return False

        payload = {
            "transmission_id": normalized["paypal-transmission-id"],
            "transmission_time": normalized["paypal-transmission-time"],
            "cert_url": normalized["paypal-cert-url"],
            "auth_algo": normalized["paypal-auth-algo"],
            "transmission_sig": normalized["paypal-transmission-sig"],
            "webhook_id": self._settings.paypal_webhook_id,
            "webhook_event": raw_body.decode("utf-8"),
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                # We need a token to call the verification endpoint
                token_response = client.post(
                    f"{self._base_url}/v1/oauth2/token",
                    auth=(
                        self._settings.paypal_client_id,
                        self._settings.paypal_client_secret.get_secret_value(),
                    ),
                    data={"grant_type": "client_credentials"},
                )
                if token_response.status_code != 200:
                    return False
                token = token_response.json()["access_token"]

                response = client.post(
                    f"{self._base_url}/v1/notifications/verify-webhook-signature",
                    headers={"Authorization": f"Bearer {token}"},
                    json=payload,
                )
                if response.status_code != 200:
                    return False
                return response.json().get("verification_status") == "SUCCESS"
        except (httpx.HTTPError, ValueError, KeyError):
            return False
