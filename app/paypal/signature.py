"""Webhook signature verification (F1-19 / DEC-24)."""

import json
from collections.abc import Mapping
from typing import Final, Protocol
from urllib.parse import urlsplit

import httpx

from app.core.config import Settings

# DEC-24: these are the only hosts PayPal is allowed to point us at for certificate URLs.
ALLOWED_CERT_HOSTS: Final = frozenset(
    {
        "api.paypal.com",
        "api-m.paypal.com",
        "api.sandbox.paypal.com",
        "api-m.sandbox.paypal.com",
    }
)
CERT_PATH_PREFIX: Final = "/v1/notifications/certs/"


class WebhookVerifier(Protocol):
    def verify(self, headers: Mapping[str, str], raw_body: bytes) -> bool: ...


class MockWebhookVerifier:
    """Accepts every payload. Valid only when PAYPAL_MODE=mock."""

    def verify(self, headers: Mapping[str, str], raw_body: bytes) -> bool:
        return True


def is_trusted_cert_url(cert_url: str) -> bool:
    """Validate cert_url before any outbound call (defence in depth, DEC-24)."""
    try:
        parts = urlsplit(cert_url)
        return (
            parts.scheme == "https"
            and parts.hostname in ALLOWED_CERT_HOSTS
            and parts.port in (None, 443)
            and not parts.username
            and not parts.password
            and parts.path.startswith(CERT_PATH_PREFIX)
            and ".." not in parts.path
        )
    except Exception:
        return False


class PayPalApiWebhookVerifier:
    """Calls the official PayPal endpoint to verify the signature (DEC-24).

    This avoids downloading the cert_url (SSRF risk) and relies on PayPal's own infrastructure.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base_url = str(settings.paypal_base_url).rstrip("/")

    def verify(self, headers: Mapping[str, str], raw_body: bytes) -> bool:
        required = {
            "paypal-transmission-id",
            "paypal-transmission-time",
            "paypal-cert-url",
            "paypal-auth-algo",
            "paypal-transmission-sig",
        }
        normalized = {k.lower(): v for k, v in headers.items()}
        if not required.issubset(normalized.keys()):
            return False

        # 1. Validate cert_url BEFORE any outbound call.
        if not is_trusted_cert_url(normalized.get("paypal-cert-url", "")):
            return False

        # 2. Build the envelope and splice the raw body EXACTLY as the webhook_event object.
        #    Re-serializing a dict would reorder keys and may change float formatting.
        envelope_base = json.dumps(
            {
                "transmission_id": normalized["paypal-transmission-id"],
                "transmission_time": normalized["paypal-transmission-time"],
                "cert_url": normalized["paypal-cert-url"],
                "auth_algo": normalized["paypal-auth-algo"],
                "transmission_sig": normalized["paypal-transmission-sig"],
                "webhook_id": self._settings.paypal_webhook_id,
            },
            separators=(",", ":"),
        )
        content = envelope_base[:-1].encode("ascii") + b',"webhook_event":' + raw_body + b"}"

        try:
            with httpx.Client(timeout=10.0) as client:
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
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    content=content,
                )
                if response.status_code != 200:
                    return False
                return response.json().get("verification_status") == "SUCCESS"
        except (httpx.HTTPError, ValueError, KeyError):
            return False
