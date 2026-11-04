# DEC-24: Webhook signatures are verified through PayPal's official API

- **Status:** Closed
- **Phase:** 1

## Context

Downloading the certificate named in `cert_url` opens an SSRF surface and adds X.509 code to maintain.

## Decision

`PayPalApiWebhookVerifier` calls `POST /v1/notifications/verify-webhook-signature` with `PAYPAL_WEBHOOK_ID`. If `cert_url` is present it is still validated (https, exact host allow-list, `/v1/notifications/certs/` path).

## Consequences

The backend downloads nothing. There is no strict replay window because PayPal retries for days; the unique `event_id` is the defense. Manual X.509 verification is built only if the API fails in Sandbox.
