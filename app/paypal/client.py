"""Real PayPal Invoicing API v2 gateway (F1-17).

Calls are synchronous and never retried automatically: Invoicing mutations are not replay-safe,
so a failed hop is surfaced to ExecutionService (F1-18), which decides how to recover. The only
retry is one re-authentication after HTTP 401, which is safe because PayPal rejected the request
before processing it.
"""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Any

import httpx
from pydantic import TypeAdapter, ValidationError

from app.core.config import Settings
from app.core.schemas import Money
from app.paypal.gateway import (
    NewInvoiceReq,
    PayPalError,
    PayPalInvoiceRef,
    PayPalInvoiceState,
)

_MONEY_ADAPTER = TypeAdapter(Money)
_TOKEN_SKEW_SECONDS = 60
_DEFAULT_TOKEN_TTL_SECONDS = 300
_REQUEST_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
_INVOICES_PATH = "/v2/invoicing/invoices"


class RealPayPalGateway:
    """PayPal Invoicing v2 over httpx. Build once and reuse: it caches the OAuth token."""

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        secret = settings.paypal_client_secret.get_secret_value()
        missing = [
            name
            for name, present in (
                ("PAYPAL_CLIENT_ID", bool(settings.paypal_client_id)),
                ("PAYPAL_CLIENT_SECRET", bool(secret)),
                ("PAYPAL_MERCHANT_EMAIL", settings.paypal_merchant_email is not None),
            )
            if not present
        ]
        if missing:
            raise PayPalError("CONFIG_ERROR", f"Missing settings: {', '.join(missing)}")

        self._settings = settings
        self._base_url = str(settings.paypal_base_url).rstrip("/")
        self._client = client or httpx.Client(timeout=_REQUEST_TIMEOUT)
        self._access_token: str | None = None
        self._token_expires_at = 0.0

    def close(self) -> None:
        self._client.close()

    # ------------------------------------------------------------------ transport

    def _get_access_token(self, *, force_refresh: bool = False) -> str:
        if (
            not force_refresh
            and self._access_token is not None
            and time.monotonic() < self._token_expires_at
        ):
            return self._access_token

        try:
            response = self._client.post(
                f"{self._base_url}/v1/oauth2/token",
                auth=httpx.BasicAuth(
                    self._settings.paypal_client_id,
                    self._settings.paypal_client_secret.get_secret_value(),
                ),
                data={"grant_type": "client_credentials"},
            )
        except httpx.HTTPError as err:
            # The mutation was never sent, so this is not an "outcome unknown" failure.
            raise PayPalError(
                "AUTH_UNREACHABLE", f"Could not reach PayPal OAuth: {type(err).__name__}"
            ) from err

        if response.status_code != 200:
            raise PayPalError(
                "AUTH_FAILED", f"PayPal rejected the credentials (HTTP {response.status_code})"
            )

        try:
            body = response.json()
            token = str(body["access_token"])
            ttl = int(body.get("expires_in", _DEFAULT_TOKEN_TTL_SECONDS))
        except (ValueError, KeyError, TypeError, AttributeError) as err:
            raise PayPalError("INVALID_RESPONSE", "PayPal token response is malformed") from err

        self._access_token = token
        self._token_expires_at = time.monotonic() + max(ttl - _TOKEN_SKEW_SECONDS, 0)
        return token

    def _send(self, method: str, endpoint: str, payload: dict[str, Any] | None) -> httpx.Response:
        token = self._get_access_token()
        try:
            return self._client.request(
                method,
                f"{self._base_url}{endpoint}",
                json=payload,
                headers={"Authorization": f"Bearer {token}", "Prefer": "return=representation"},
            )
        except httpx.TimeoutException as err:
            raise PayPalError("TIMEOUT", "PayPal did not answer in time") from err
        except httpx.HTTPError as err:
            raise PayPalError(
                "NETWORK_ERROR", f"Could not reach PayPal: {type(err).__name__}"
            ) from err

    @staticmethod
    def _to_error(response: httpx.Response) -> PayPalError:
        code = f"PAYPAL_HTTP_{response.status_code}"
        message = "PayPal request failed"
        try:
            body = response.json()
        except ValueError:
            return PayPalError(code, message)
        if not isinstance(body, dict):
            return PayPalError(code, message)

        message = str(body.get("message") or body.get("name") or message)
        details = body.get("details")
        if isinstance(details, list) and details and isinstance(details[0], dict):
            issue = details[0].get("issue")
            if issue:
                code = str(issue)
        debug_id = body.get("debug_id")
        if debug_id:
            message = f"{message} (debug_id={debug_id})"
        return PayPalError(code, message)

    def _request(
        self, method: str, endpoint: str, payload: dict[str, Any] | None = None
    ) -> httpx.Response:
        response = self._send(method, endpoint, payload)
        if response.status_code == 401:
            self._get_access_token(force_refresh=True)
            response = self._send(method, endpoint, payload)
        if response.status_code >= 400:
            raise self._to_error(response)
        return response

    @staticmethod
    def _json(response: httpx.Response) -> dict[str, Any]:
        try:
            body = response.json()
        except ValueError as err:
            raise PayPalError("INVALID_RESPONSE", "PayPal returned a non-JSON body") from err
        if not isinstance(body, dict):
            raise PayPalError("INVALID_RESPONSE", "PayPal returned an unexpected JSON shape")
        return body

    @staticmethod
    def _money_value(node: Any) -> str | None:
        if isinstance(node, dict) and isinstance(node.get("value"), str):
            return node["value"]
        return None

    @staticmethod
    def _extract_invoice_id(body: dict[str, Any]) -> str:
        """Read the id from a full representation or from a bare HATEOAS link."""
        invoice_id = body.get("id")
        if isinstance(invoice_id, str) and invoice_id:
            return invoice_id

        hrefs: list[Any] = [body.get("href")]
        links = body.get("links")
        if isinstance(links, list):
            hrefs.extend(
                link.get("href")
                for link in links
                if isinstance(link, dict) and link.get("rel") == "self"
            )
        for href in hrefs:
            if isinstance(href, str) and href:
                tail = href.rstrip("/").rsplit("/", 1)[-1]
                if tail:
                    return tail
        raise PayPalError("INVALID_RESPONSE", "PayPal did not return an invoice ID")

    # ------------------------------------------------------------------ port

    def create_draft(self, req: NewInvoiceReq, request_id: str) -> PayPalInvoiceRef:
        # PayPal Invoicing has no replay-safe creation (spike F1-03): duplicates are rejected
        # with 422 DUPLICATE_INVOICE_NUMBER. request_id is persisted by ExecutionService and
        # is deliberately not forwarded.
        del request_id

        recipient = self._settings.paypal_sandbox_buyer_email or req.recipient_email
        if recipient is None:
            raise PayPalError(
                "CONFIG_ERROR",
                "No recipient email in the request or in PAYPAL_SANDBOX_BUYER_EMAIL",
            )

        payload: dict[str, Any] = {
            "detail": {
                "invoice_number": req.invoice_number,
                "currency_code": req.currency,
                "payment_term": {"term_type": "DUE_ON_RECEIPT"},
            },
            "invoicer": {"email_address": str(self._settings.paypal_merchant_email)},
            "primary_recipients": [{"billing_info": {"email_address": str(recipient)}}],
            "items": [
                {
                    "name": "Recovery Proposal",
                    "quantity": "1",
                    "unit_amount": {"currency_code": req.currency, "value": req.amount},
                }
            ],
        }
        body = self._json(self._request("POST", _INVOICES_PATH, payload))
        status = body.get("status")
        return PayPalInvoiceRef(
            id=self._extract_invoice_id(body),
            status=status if isinstance(status, str) and status else "DRAFT",
        )

    def cancel_invoice(self, paypal_invoice_id: str) -> None:
        payload = {
            "subject": "Invoice Cancelled",
            "note": "Renegotiation accepted",
            "send_to_recipient": True,
        }
        self._request("POST", f"{_INVOICES_PATH}/{paypal_invoice_id}/cancel", payload)

    def send_invoice(self, paypal_invoice_id: str) -> PayPalInvoiceRef:
        self._request(
            "POST", f"{_INVOICES_PATH}/{paypal_invoice_id}/send", {"send_to_invoicer": True}
        )
        # The send response carries no status; PayPal reports SENT afterwards (spike F1-03).
        return PayPalInvoiceRef(id=paypal_invoice_id, status="SENT")

    def delete_draft(self, paypal_invoice_id: str) -> None:
        self._request("DELETE", f"{_INVOICES_PATH}/{paypal_invoice_id}")

    def get_invoice(self, paypal_invoice_id: str) -> PayPalInvoiceState:
        body = self._json(self._request("GET", f"{_INVOICES_PATH}/{paypal_invoice_id}"))

        # Fail closed: the preflight must never run on an invented status.
        status = body.get("status")
        if not isinstance(status, str) or not status:
            raise PayPalError("INVALID_RESPONSE", "PayPal invoice has no status")

        payments = body.get("payments")
        paid_node = payments.get("paid_amount") if isinstance(payments, dict) else None
        return PayPalInvoiceState(
            id=paypal_invoice_id,
            status=status,
            amount_due=self._money_value(body.get("due_amount")),
            total_amount=self._money_value(body.get("amount")),
            paid_amount=self._money_value(paid_node),
        )

    def record_payment(self, paypal_invoice_id: str, amount: str) -> None:
        if not self._settings.allow_sandbox_payment_shortcut or "sandbox" not in self._base_url:
            raise PayPalError("SANDBOX_ONLY", "Payment shortcut is only permitted in Sandbox")

        try:
            validated = _MONEY_ADAPTER.validate_python(amount)
        except (ValidationError, ValueError) as err:
            raise PayPalError("INVALID_AMOUNT", "Amount must be a valid Money string") from err
        if Decimal(validated) <= Decimal("0.00"):
            raise PayPalError("INVALID_AMOUNT", "Payment amount must be greater than zero")

        payload = {
            "method": "OTHER",
            "amount": {"currency_code": "USD", "value": validated},
            "note": "Merchant-recorded payment (Sandbox)",
        }
        self._request("POST", f"{_INVOICES_PATH}/{paypal_invoice_id}/payments", payload)
