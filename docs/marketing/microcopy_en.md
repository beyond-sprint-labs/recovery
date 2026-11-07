# Interface Microcopy & Deterministic Templates

## 1. UI Buttons & Action Copy
- **Approve Option:** `Approve this option`
- **Accept Plan:** `Accept`
- **Decline Plan:** `Decline`
- **Refresh Status:** `Refresh from PayPal`

### Mandatory Legal Disclaimer
> *"Simulation subject to merchant approval and customer acceptance. Not financial or legal advice."*

---

## 2. Deterministic Approval Templates
These templates are used by the backend server to generate the final single-option message for the customer when the merchant approves an alternative:

### Settlement with Discount (settlement_discount)
`Hello, your proposed settlement terms for invoice {invoice_id} have been approved. You can settle the full balance today with a single payment of ${amount_due_now} ({discount_pct}% discount). Please review the terms and confirm below.`

### Down Payment + Installments (down_payment_installments)
`Hello, your proposed installment arrangement for invoice {invoice_id} has been approved: pay ${amount_due_now} today, followed by {installments} monthly payments of ${installment_amount}, for a total of ${total_paid}. Please review the schedule and confirm below.`