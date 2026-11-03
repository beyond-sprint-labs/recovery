# PayPal Invoicing refinancing exploration

## Status and scope

This hackathon exploration tested two ways to represent an agreed monthly repayment plan through PayPal Invoicing API v2 in Sandbox. It records observed REST behavior and proposes a direction for integration review.

**This is exploratory evidence, not a production integration or an implementation proposal ready to merge into the application.** No application routes, LangGraph tools, persistence, payment allocation, webhook handlers or customer approval workflow are implemented by this document. The local experiment scripts and raw account responses are outside this PR.

## Experiment terms

Both scenarios were independent tests with identical financial terms:

| Parameter | Value |
|---|---:|
| Original consumption | MXN 100.00 |
| Down payment received | MXN 30.00 |
| Remaining principal | MXN 70.00 |
| Contractual valuation date | 2026-11-02 |
| First installment due | 2026-12-02 |
| Final installment due | 2027-11-02 |
| Number of monthly installments | 12 |
| Effective monthly rate | 2% |
| Nominal annual input to finance utilities | 24% |
| Equivalent effective annual rate | Approximately 26.824179% |
| Collectible payments | 11 payments of MXN 6.62 and a final MXN 6.61 |
| Total financed payments | MXN 79.43 |
| Total financing interest | MXN 9.43 |

Periods are contractual months, not actual elapsed days. The finance utilities generated the annuity and monthly dates; the exploratory collection adapter reconciled cents on rounded balances and adjusted the last installment. No discount or debt forgiveness was applied in these experiments.

## REST observations

### Common starting point

For each scenario, an invoice for MXN 100 was created and sent through the API, with partial payments enabled. The Sandbox buyer authorized a MXN 30 payment through PayPal Checkout. A subsequent GET confirmed `PARTIALLY_PAID`, paid amount `30.00`, and outstanding amount `70.00` before refinancing.

### Scenario A: update the original invoice

A full PUT preserved the original MXN 100 consumption line and added a separate MXN 9.43 line labeled as interest under the agreed financing plan. The customer-visible note included rates, terms and the complete amortization table.

The follow-up GET confirmed:

- Invoice total: MXN 109.43.
- Previous payment retained: MXN 30.00.
- Outstanding amount: MXN 79.43.
- Status: `PARTIALLY_PAID`.
- Partial-payment minimum: MXN 6.62.
- Invoice-level due date: 2027-11-02.

**One invoice has one invoice-level due date.** The twelve installment dates appeared in the note; this did not create twelve independently enforced due dates or automatic debits. The minimum partial-payment amount is not a native installment scheduler. Its behavior when the final outstanding amount is below MXN 6.62 was not tested.

The update endpoint requires a complete invoice request rather than a partial patch; it also supports recipient update notifications. [PayPal update reference](https://developer.paypal.com/api/invoicing/v2/invoices-update/)

### Scenario B: twelve invoices with separate principal and interest

Twelve draft invoices were created, each with its own due date and two line items: a share of the original consumption principal and financing interest. Each note contained the complete plan.

An attempt to cancel the partially paid original returned HTTP 422 with `CANNOT_CANCEL_PAID_INVOICE`. Cancellation was not a usable balance-transfer mechanism in this test.

The tested alternative changed the original invoice to represent the MXN 30 down payment already received. Its description and note documented the original MXN 100 consumption and the transfer of the remaining MXN 70 to the twelve new invoices. The follow-up GET confirmed total `30.00`, paid `30.00`, outstanding `0.00`, and status `PAID`. No refund was requested.

Only after that check were the twelve replacement invoices sent. Follow-up GET requests verified all twelve as `SENT`, with the expected dates and two separate line items. Their principal sums to MXN 70.00 and their interest to MXN 9.43.

This accepted Sandbox update is **not a reviewed accounting treatment** for transferring receivables. Rewriting the original invoice changes its representation of the original sale and needs explicit accounting, audit and integration review.

## Amortization schedule

| Period | Due date | Principal (MXN) | Interest (MXN) | Payment (MXN) | Closing balance (MXN) |
|---|---|---:|---:|---:|---:|
| 0 | 2026-11-02 | 0.00 | 0.00 | 0.00 | 70.00 |
| 1 | 2026-12-02 | 5.22 | 1.40 | 6.62 | 64.78 |
| 2 | 2027-01-02 | 5.32 | 1.30 | 6.62 | 59.46 |
| 3 | 2027-02-02 | 5.43 | 1.19 | 6.62 | 54.03 |
| 4 | 2027-03-02 | 5.54 | 1.08 | 6.62 | 48.49 |
| 5 | 2027-04-02 | 5.65 | 0.97 | 6.62 | 42.84 |
| 6 | 2027-05-02 | 5.76 | 0.86 | 6.62 | 37.08 |
| 7 | 2027-06-02 | 5.88 | 0.74 | 6.62 | 31.20 |
| 8 | 2027-07-02 | 6.00 | 0.62 | 6.62 | 25.20 |
| 9 | 2027-08-02 | 6.12 | 0.50 | 6.62 | 19.08 |
| 10 | 2027-09-02 | 6.24 | 0.38 | 6.62 | 12.84 |
| 11 | 2027-10-02 | 6.36 | 0.26 | 6.62 | 6.48 |
| 12 | 2027-11-02 | 6.48 | 0.13 | 6.61 | 0.00 |

The unrounded theoretical payment is MXN 6.619171763606602. The present value of the collectible, cent-rounded payments at 2% monthly is MXN 70.00087395071591; the difference from MXN 70 is below one cent. The final balance is zero under the disclosed per-installment rounding convention. This distinction needs to remain visible in financial validation.

## Recommended direction: one invoice, one versioned repayment agreement

**Scenario A is the conceptually cleaner starting point for integration review.** It retains one invoice identity, the original consumption line and the existing payment history. Financing is explicit as a separate line item, while Recovery holds the versioned agreement and its installment calendar.

This recommendation prioritizes continuity of the receivable and audit trail. It is not a claim that PayPal natively enforces the calendar. Recovery would need to own installment-level due dates, payment allocation, reminders, arrears and agreement revisions.

Scenario B makes each due date native to an invoice, but adds twelve payment resources, more notifications, partial-failure recovery and a receivable-transfer problem. It remains an alternative if invoice-level installment tracking is essential and the team approves a sound treatment of the original balance. The exploratory rewriting technique should not become the default simply because the API accepted it.

## Customer transparency and PDF attachments

A customer-facing agreement should distinguish original consumption, prior payments, any discount or debt forgiveness, refinanced principal, monthly and annual rate conventions, financing charges, total payable and the full dated principal/interest/balance schedule. A discount should remain distinguishable from a transfer of balance.

An amortization **PDF can be generated from the approved schedule and attached to each relevant invoice**: the single invoice in A, or every installment invoice in B. A stable agreement ID and version should connect the invoice, note and PDF so the customer sees the same terms in every representation. The full original sale should not be confused with the remaining financed principal.

PayPal documents invoice attachment references in `detail.attachments`, including a file reference URL and content type. [Invoice attachment schema](https://developer.paypal.com/api/invoicing/v2/invoices-update/)

PDF generation, file storage or upload, access control, attachment delivery and the customer download experience remain integration work. **No PDF or TXT attachment was uploaded in this exploration.** A TXT table was generated locally, and the complete table was included in customer-visible invoice notes. Attachment support in the schema is not evidence of successful end-to-end attachment delivery.

## Proposed action plan: review before implementation

1. **Review the representation.** Agree whether one original invoice plus a Recovery agreement is the preferred model. Confirm accounting treatment of financing, discounts, payment history and future revisions. Keep B as a fallback, not a parallel collectible debt.
2. **Review platform and contractual applicability.** Confirm which PayPal product and merchant/customer jurisdictions apply to merchant-added financing charges. Sandbox acceptance is a technical result, not contractual authorization or a regulatory rate disclosure.
3. **Define the integration contract.** Specify invoice ID, agreement ID/version, approved terms, schedule, prior payments and rounding. Separate calculation, approval, PayPal mutation, persistence and reconciliation. Decide how to detect invoice changes between proposal and execution.
4. **Review disclosures.** Agree on visible item descriptions, rate terminology, a versioned amortization PDF and its attachment delivery. Define early repayment, partial payments, overpayments, discounts and refunds before describing customer obligations.
5. **Design reconciliation and failure handling.** Map payment IDs to allocations; verify webhook signatures, handle duplicate events, and re-query invoice state. Review retries and partial failures before any multi-invoice execution.
6. **Approve a bounded implementation slice.** After these reviews, implement one end-to-end Sandbox path from merchant-approved terms to invoice update and reconciled payment. Keep execution outside the current calculation-only scope until that decision is explicit.

**No application implementation is included in this PR.** These steps are proposed review decisions, not completed features or an expanded delivery commitment.

## Evidence and limits

The local evidence includes pre-update GET responses for both bases, a post-update A response, the B original and all twelve final invoice responses, a CSV of the installment amounts/dates, and a verification summary. Credentials, customer emails, payment URLs and raw account responses are not published with this report.

The tests establish that the described Sandbox mutations and reads succeeded for these examples. They do not establish automatic debits, legally enforceable promissory notes, discount handling, early-settlement behavior, production eligibility, attachment delivery or a completed Recovery integration.
