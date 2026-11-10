"""Gateway selection by configuration only, never by request data."""

from app.core.config import Settings
from app.paypal.client import RealPayPalGateway
from app.paypal.gateway import PayPalError, PayPalGateway
from app.paypal.mock_gateway import MockPayPalGateway
from app.paypal.signature import MockWebhookVerifier, PayPalApiWebhookVerifier, WebhookVerifier


def build_gateway(settings: Settings) -> PayPalGateway:
    """Build the gateway selected by PAYPAL_MODE.

    Call it once at wiring time and reuse the instance: the mock keeps its invoices in memory
    and the real client caches its OAuth token.
    """
    if settings.paypal_mode == "real":
        return RealPayPalGateway(settings)
    if settings.paypal_mode == "mock":
        return MockPayPalGateway()
    raise PayPalError("CONFIG_ERROR", f"Unknown PAYPAL_MODE: {settings.paypal_mode}")


def build_webhook_verifier(settings: Settings) -> WebhookVerifier:
    """Build the webhook verifier by configuration, never by request data (DEC-24)."""
    if settings.paypal_mode == "real":
        return PayPalApiWebhookVerifier(settings)
    return MockWebhookVerifier()
