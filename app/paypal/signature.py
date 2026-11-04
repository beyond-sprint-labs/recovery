"""Webhook signature verification port (F1-09).

The verifier is chosen only by configuration (PAYPAL_MODE) when the application
is wired, never from request headers or body.
"""

from collections.abc import Mapping
from typing import Protocol


class WebhookVerifier(Protocol):
    """Port implemented by the real PayPal API verifier and by the mock."""

    def verify(self, headers: Mapping[str, str], raw_body: bytes) -> bool:
        """Return True only if the webhook is authentic."""
        ...


class MockWebhookVerifier:
    """Accepts every payload. Valid only when PAYPAL_MODE=mock (demo and tests)."""

    def verify(self, headers: Mapping[str, str], raw_body: bytes) -> bool:
        return True
