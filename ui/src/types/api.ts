/**
 * Strict TypeScript types for DueGuide Frontend
 * Adheres to DEC-02 (Money strictly as decimal string)
 * Generated from contracts/examples/
 */

export interface Actor {
  type: 'SYSTEM' | 'MERCHANT' | 'CUSTOMER' | 'PAYPAL' | 'AGENT' | string;
  id: string;
}

export interface RuleViolation {
  code: string;
  limit: string | null;
  attempted: string | null;
  unit?: string;
  message?: string;
}

export interface AuditEvent {
  event_id: string;
  seq: number;
  ts: string;
  actor: Actor;
  action: string;
  invoice_id: string;
  proposal_id: string | null;
  state_from: string | null;
  state_to: string;
  severity: 'INFO' | 'WARNING' | 'CRITICAL';
  rule: RuleViolation | null;
  summary: string;
  proposed_by: {
    type: string;
    id: string;
    mode?: string;
  } | null;
  paypal_called: boolean;
  source: string | null;
  paypal_ref: string | null;
}

export interface Invoice {
  id: string;
  customer_id?: string;
  customer_name: string;
  currency: string;
  balance: string; // Strictly decimal string, e.g. "1000.00"
  due_date: string;
  status: 'OVERDUE' | 'PAID' | 'CANCELLED' | string;
  paypal_invoice_id: string | null;
}

export interface ScheduleItem {
  n: number;
  due_date: string;
  amount: string;
  principal: string;
  interest: string;
}

export interface AlternativeTerms {
  discount_pct?: string;
  down_payment_pct?: string;
  installments?: number;
  periodic_rate_pct?: string;
}

export interface Alternative {
  type: 'settlement_discount' | 'down_payment_installments';
  terms: AlternativeTerms;
  amount_due_now: string;
  installment_amount: string | null;
  total_paid: string;
  present_value?: string;
  financing_cost?: string;
  merchant_difference_vs_balance?: string;
  policy_ok?: boolean;
  violations?: RuleViolation[];
  schedule: ScheduleItem[];
}

export interface Proposal {
  proposal_id: string;
  invoice_id: string;
  status:
    | 'PENDING_MERCHANT'
    | 'APPROVED'
    | 'BLOCKED'
    | 'PENDING_CUSTOMER'
    | 'ACCEPTED'
    | 'DECLINED'
    | 'EXECUTING'
    | 'EXECUTED'
    | 'FAILED'
    | 'NEEDS_RECONCILIATION'
    | 'PAID';
  engine_version?: string;
  currency: string;
  customer_intent?: {
    available_now: string | null;
    preferred_installments: number | null;
    requested_discount_pct: string | null;
    desired_date: string | null;
  };
  alternatives: Alternative[];
  customer_message?: string;
  block_reason?: string;
  policy_violations?: RuleViolation[];
}

export interface CustomerProposalView {
  proposal_id: string;
  invoice_id: string;
  currency: string;
  original_balance: string;
  alternative: Alternative;
  customer_message: string;
  expires_at: string;
  status: string;
  simulation_notice: string;
}

export interface ApproveRequest {
  alternative_type: 'settlement_discount' | 'down_payment_installments';
  note?: string | null;
}

export interface ApproveResponse {
  proposal_id: string;
  status: 'PENDING_CUSTOMER';
  approved_alternative: Alternative;
  customer_link: string;
  customer_token_expires_at: string;
  audit_events: AuditEvent[];
}

export interface CustomerRespondRequest {
  decision: 'ACCEPT' | 'DECLINE';
}

export interface CustomerRespondResponse {
  proposal_id: string;
  status: 'EXECUTED' | 'FAILED' | 'NEEDS_RECONCILIATION' | 'DECLINED';
  paypal?: {
    new_invoice_id: string;
    original_invoice_id: string;
    steps: Array<{
      step: string;
      status: 'OK' | 'FAILED';
      paypal_id?: string;
    }>;
  };
  audit_events?: AuditEvent[];
}
