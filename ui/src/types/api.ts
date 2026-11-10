// ---------- Primitives ----------
export type Money = string;         // "900.00"
export type SignedMoney = string;   // "-100.00"
export type Pct = string;           // "10" | "10.5"
export type Currency = "USD";
export type IsoDate = string;       // "YYYY-MM-DD"
export type IsoDateTime = string;   // "YYYY-MM-DDTHH:MM:SSZ"

// ---------- States ----------
export type ProposalStatus =
  | "DRAFTED"
  | "PENDING_MERCHANT"
  | "BLOCKED"
  | "APPROVED"
  | "PENDING_CUSTOMER"
  | "ACCEPTED"
  | "EXECUTING"
  | "EXECUTED"
  | "PAID"
  | "REJECTED"
  | "DECLINED"
  | "EXPIRED"
  | "FAILED"
  | "NEEDS_RECONCILIATION";

export type AlternativeType = "settlement_discount" | "down_payment_installments";
export type Severity = "INFO" | "WARN" | "CRITICAL";

// ---------- Invoice ----------
export interface Invoice {
  id: string;
  customer_name: string;
  currency: Currency;
  balance: Money;
  due_date: IsoDate;
  status: "OVERDUE" | "PAID" | "CANCELLED";
  paypal_invoice_id: string | null;
}

// ---------- Policy ----------
export interface Policy {
  currency: Currency;
  max_discount_pct: Pct;
  min_down_payment_pct: Pct;
  max_installments: number;
  max_financing_rate_pct: Pct;
  merchant_discount_rate_pct: Pct;
}

// ---------- Proposal ----------
export interface CustomerIntent {
  available_now: Money | null;
  preferred_installments: number | null;
  requested_discount_pct: Pct | null;
  desired_date: IsoDate | null;
}

export interface ScheduleItem {
  n: number;
  due_date: IsoDate;
  amount: Money;
  principal: Money;
  interest: Money;
}

export interface Alternative {
  type: AlternativeType;
  terms: Record<string, string | number>;
  amount_due_now: Money;
  installment_amount: Money | null;
  total_paid: Money;
  present_value: Money;
  financing_cost: Money;
  merchant_difference_vs_balance: SignedMoney;
  policy_ok: boolean;
  schedule: ScheduleItem[];
}

export interface BlockedReason {
  code: string;
  message: string;
  limit: string;
  attempted: string;
  unit: string;
}

export interface PolicyViolation {
  code: string;
  limit: string;
  attempted: string;
  unit: string;
}

export interface PolicyCheck {
  status: "PASSED" | "BLOCKED";
  violations: PolicyViolation[];
}

export interface TextNumberCheck {
  status: "PASSED" | "FAILED" | "SKIPPED";
  numbers_in_text: string[];
  unmatched: string[];
}

export interface AttemptedAlternative {
  type: AlternativeType;
  terms: Record<string, string | number>;
  computed: { amount_due_now: Money; merchant_difference_vs_balance: SignedMoney };
}

export interface AuditActor {
  type: "SYSTEM" | "AGENT" | "MERCHANT" | "CUSTOMER" | "PAYPAL";
  id: string;
}

export interface RuleHit {
  code: string;
  limit: string;
  attempted: string;
  unit: string;
}

export interface AuditEvent {
  event_id: string;
  seq: number;
  ts: IsoDateTime;
  actor: AuditActor;
  action: string;
  invoice_id: string | null;
  proposal_id: string | null;
  state_from: ProposalStatus | null;
  state_to: ProposalStatus | null;
  severity: Severity;
  rule: RuleHit | null;
  summary: string;
  paypal_called: boolean;
  source?: string | null;
  paypal_ref?: string | null;
}

// ---------- ProposalOut (union of A/B/C) ----------
export interface ProposalOut {
  proposal_id: string;
  invoice_id: string;
  status: ProposalStatus;
  engine_version: string;
  currency: Currency;
  customer_intent: CustomerIntent;
  alternatives: Alternative[];              // [] when BLOCKED
  attempted?: AttemptedAlternative[];       // only when BLOCKED
  blocked_reasons?: BlockedReason[];        // only when BLOCKED
  explanation: string | null;
  customer_message_draft: string | null;
  policy_check: PolicyCheck;
  text_number_check: TextNumberCheck;
  paypal_called: boolean;
  audit_event: AuditEvent;
}

// ---------- CreateProposal ----------
export interface CreateProposalIn {
  customer_message: string;
  scenario_id?: string | null;
}

// ---------- Approve ----------
export interface ApproveIn {
  alternative_type: AlternativeType;
  note?: string | null;
}

export interface ApproveOut {
  proposal_id: string;
  status: "PENDING_CUSTOMER";
  approved_alternative: AlternativeType;
  customer_link: string;
  customer_token_expires_at: IsoDateTime;
  audit_events: AuditEvent[];
}

// ---------- Reject ----------
export interface RejectIn {
  note?: string | null;
}
export interface RejectOut {
  proposal_id: string;
  status: "REJECTED";
  audit_events: AuditEvent[];
}

// ---------- Customer view ----------
export interface CustomerAlternativeView {
  type: AlternativeType;
  terms: Record<string, string | number>;
  amount_due_now: Money;
  installment_amount: Money | null;
  total_paid: Money;
  schedule: ScheduleItem[];
}

export interface CustomerProposalView {
  proposal_id: string;
  invoice_id: string;
  currency: Currency;
  original_balance: Money;
  alternative: CustomerAlternativeView;
  customer_message: string;
  expires_at: IsoDateTime;
  status: ProposalStatus;
  simulation_notice: string;
}

export interface RespondIn {
  decision: "ACCEPT" | "DECLINE";
}

export interface PayPalStep {
  name: string;
  status: "OK" | "FAILED" | "SKIPPED";
  ref?: string | null;
  at?: IsoDateTime;
}

export interface PayPalExecution {
  new_invoice_id: string | null;
  original_invoice_id: string | null;
  steps: PayPalStep[];
}

export interface RespondOut {
  proposal_id: string;
  status: ProposalStatus;
  paypal: PayPalExecution | null;
  audit_events: AuditEvent[];
}

export interface ReconcileOut {
  proposal_id: string;
  status: ProposalStatus;
  audit_events: AuditEvent[];
}

// ---------- Audit page ----------
export interface AuditEventsPage {
  items: AuditEvent[];
  next_seq: number;
}

// ---------- Errors ----------
export interface ApiError {
  error: { code: string; message: string };
}