# PayPal Invoicing API v2 Sandbox Spike & Anti-Double-Charge Verification

- **Task Reference:** F1-03
- **Status:** Closed / Empirically Verified
- **Environment:** PayPal Sandbox (`https://api-m.sandbox.paypal.com`)
- **API Version:** Invoicing API v2
- **Currency:** USD

---

## 1. Executive Summary & Verification of Invariant DEC-15 (AC11)

This spike provides empirical verification of the core operations in PayPal Invoicing API v2 to guarantee the **Anti-Double-Charge Invariant (AC11 / DEC-15)**:

$$\text{Preflight} \longrightarrow \text{Create Draft} \longrightarrow \text{Cancel Original (204)} \longrightarrow \text{Send Draft (200)}$$

All operations were executed against Sandbox accounts using Postman to verify HTTP response codes, measured latencies, idempotency constraints, and sandbox payment mechanisms.

---

## 2. Empirical Verification Matrix (Postman Sandbox Evidence)

| Step | Operation | Endpoint | HTTP Status | Measured Latency | Observed Result / Artifact |
|---|---|---|:---:|:---:|---|
| 1 | Create Draft A | `POST /v2/invoicing/invoices` | **201 Created** | 1.17 s | Draft invoice ID issued (`INV2-2PCM-NCBE-AL76-RWMN`) |
| 2 | Deduplication Check | `POST /v2/invoicing/invoices` | **422 Unprocessable** | 820 ms | `DUPLICATE_INVOICE_NUMBER` (`debug_id: f151839b11c4d`) |
| 3 | Send Invoice A | `POST /v2/invoicing/invoices/{id}/send` | **200 OK** | 1.34 s | Invoice `#INV2-2PCM-NCBE-AL76-RWMN` moved to sent |
| 4 | Create Draft B | `POST /v2/invoicing/invoices` | **201 Created** | 825 ms | Replacement draft issued (`INV2-NBPL-EWU4-NB3J-BPQ5`) |
| 5 | Cancel Original A | `POST /v2/invoicing/invoices/{id}/cancel` | **204 No Content** | 886 ms | Original invoice cancelled with recipient notification |
| 6 | Send Invoice B | `POST /v2/invoicing/invoices/{id}/send` | **200 OK** | 903 ms | Replacement invoice sent to customer |
| 7 | Rollback Test (Draft C) | `DELETE /v2/invoicing/invoices/{id}` | **204 No Content** | 871 ms | Draft `INV2-6973-AWM6-YBNF-P2LZ` purged from storage |
| 8 | Record Payment (Shortcut) | `POST /v2/invoicing/invoices/{id}/payments` | **200 OK** | 1.78 s | Payment recorded (`payment_id: EXTR-67910647YM891240V`) |
| 9 | Webhook Signature Check | `POST /v1/notifications/verify-webhook-signature` | **200 OK** | 451 ms | Verification status: `SUCCESS` |

---

## 3. Creation & Deduplication Analysis

### 3.1. Successful Creation
* **Endpoint:** `POST /v2/invoicing/invoices`
* **Response:** HTTP `201 Created`
```json
{
    "rel": "self",
    "href": "https://api.sandbox.paypal.com/v2/invoicing/invoices/INV2-2PCM-NCBE-AL76-RWMN",
    "method": "GET"
}
```

### 3.2. Idempotency Finding: PayPal rejects duplicates on creation
PayPal Invoicing API v2 does not return an idempotent replay when an invoice number already exists; it rejects the call:

* **Request:** `POST /v2/invoicing/invoices` with `invoice_number: "INV-TEST-A-V2"`
* **Observed Response (HTTP 422 Unprocessable Entity):**
```json
{
  "name": "UNPROCESSABLE_ENTITY",
  "message": "The requested action could not be performed, semantically incorrect, or failed business validation.",
  "debug_id": "f151839b11c4d",
  "details": [
    {
      "field": "/detail/invoice_number",
      "value": "INV-TEST-A-V2",
      "location": "body",
      "issue": "DUPLICATE_INVOICE_NUMBER",
      "description": "Invoice number is duplicate."
    }
  ],
  "links": [
    {
      "href": "https://developer.paypal.com/docs/api/invoicing/#errors",
      "method": "GET"
    }
  ]
}
```

* **Architectural Enforcement:** Deduplication is strictly handled by the Recovery backend by persisting `draft_id` locally before executing cancellation.

---

## 4. Atomic Replacement Sequence Verification

### 4.1. Sending Invoice A
* **Endpoint:** `POST /v2/invoicing/invoices/INV2-2PCM-NCBE-AL76-RWMN/send`
* **Payload:** `{"send_to_invoicer": true}`
* **Response:** HTTP `200 OK` (1.34 s)
* **Status Verification Note:** After executing `/send`, an immediate `GET /v2/invoicing/invoices/{id}` returns a status of **`SENT`**. The `UNPAID` status is only observed later in the payment lifecycle (or when viewed from the recipient's perspective). The `ExecutionService` preflight logic must explicitly check for `SENT` to confirm the invoice was dispatched.

### 4.2. Cancelling Original Invoice A
* **Endpoint:** `POST /v2/invoicing/invoices/INV2-2PCM-NCBE-AL76-RWMN/cancel`
* **Payload:**
```json
{
  "subject": "Cancellation Test",
  "note": "Cancelling sent invoice for MVP renegotiation",
  "send_to_recipient": true
}
```
* **Response:** HTTP `204 No Content` (886 ms).
* **Preflight Safeguard:** As verified in the partial payment exploration (`paypal_partial_payments_spike.md`), invoices with recorded payments return HTTP `422 CANNOT_CANCEL_PAID_INVOICE`. The preflight step in `ExecutionService` must abort if an invoice is in `PARTIALLY_PAID` or `PAID` status.

### 4.3. Sending Replacement Invoice B
* **Endpoint:** `POST /v2/invoicing/invoices/INV2-NBPL-EWU4-NB3J-BPQ5/send`
* **Response:** HTTP `200 OK`.

### 4.4. Rollback via Delete Draft (Draft C)
* **Endpoint:** `DELETE /v2/invoicing/invoices/INV2-6973-AWM6-YBNF-P2LZ`
* **Response:** HTTP `204 No Content` (871 ms).
* **Guaranteed Invariant:** If cancellation of the original fails, `delete_draft` purges the newly created draft, ensuring only one payable invoice exists at all times.

---

## 5. Sandbox Payment Shortcut & Webhook Dispatch

* **Endpoint:** `POST /v2/invoicing/invoices/INV2-NBPL-EWU4-NB3J-BPQ5/payments`
* **Payload:**
```json
{
  "method": "OTHER",
  "amount": {
    "currency_code": "USD",
    "value": "100.00"
  },
  "note": "Simulating full payment to trigger webhook"
}
```
* **Strict Contract Rule:** The payment field is strictly named `"method"`. Submitting `"payment_method"` results in HTTP `400 BAD_REQUEST`.
* **Response:** HTTP `200 OK` (1.78 s) with `payment_id: "EXTR-67910647YM891240V"`.
* **Webhook Confirmation:** Recording a payment via this endpoint triggers an authentic `INVOICING.INVOICE.PAID` asynchronous event dispatched by PayPal Sandbox.

---

## 6. Webhook Signature Verification Architecture (DEC-24)

Instead of downloading external public certificates via `cert_url` (which introduces SSRF risks), signature verification routes to PayPal's official endpoint:
`POST /v1/notifications/verify-webhook-signature` using `PAYPAL_WEBHOOK_ID`.

* **Observed Verification Response:**
```json
{
  "verification_status": "SUCCESS"
}
```

---

## 7. Conclusions for Production Architecture
1. **Network Hops & DB Locks:** The entire atomic sequence takes between 2.5 and 4.0 seconds. No database transaction may be held open during these external calls.
2. **Failure Handling (`NEEDS_RECONCILIATION`):** If step 6 (`send B`) fails after step 5 (`cancel A`), the original invoice cannot be un-cancelled. The proposal moves to `NEEDS_RECONCILIATION`, where `POST /proposals/{id}/reconcile` strictly retries sending the draft invoice.
