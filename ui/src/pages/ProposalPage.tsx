import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import {
  approveProposal,
  getProposal,
  isMockMode,
  reconcileProposal,
  rejectProposal,
  sandboxRecordPayment,
} from "../api/client";
import type {
  Alternative,
  ApproveOut,
  ProposalOut,
  ProposalStatus,
  ReconcileOut,
} from "../types/api";
import { formatMoney } from "../components/Money";

const ALT_LABEL: Record<string, string> = {
  settlement_discount: "Settlement Discount",
  down_payment_installments: "Down Payment + Installments",
};


const LIVE_STATUSES: ProposalStatus[] = [
  "PENDING_CUSTOMER",
  "ACCEPTED",
  "EXECUTING",
  "EXECUTED",
  "NEEDS_RECONCILIATION",
];


const AGENT_NOTICE: Record<string, { icon: string; title: string; text: string }> = {
  CLARIFICATION_REQUIRED: {
    icon: "💬",
    title: "More information needed",
    text: "The customer message does not contain enough information to build an offer. Ask the customer for details and generate a new proposal.",
  },
  INVALID_AGENT_OUTPUT: {
    icon: "🛑",
    title: "AI output rejected",
    text: "The AI response failed validation and was discarded. Generate a new proposal.",
  },
};

const rowStyle = { display: "flex", justifyContent: "space-between", fontSize: "13px" } as const;
const labelStyle = { color: "var(--text-secondary)" } as const;

function messageOf(e: unknown): string {
  return e instanceof Error ? e.message : "Unexpected error.";
}

function unitSuffix(unit?: string): string {
  if (!unit) return "";
  return unit === "pct" ? "%" : ` ${unit}`;
}


function tokenFrom(link: string): string {
  try {
    return new URL(link, window.location.origin).pathname.split("/").filter(Boolean).pop() ?? "";
  } catch {
    return link.split("/").pop() ?? "";
  }
}

export function ProposalPage() {
  const { id = "" } = useParams<{ id: string }>();

  const [proposal, setProposal] = useState<ProposalOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [approving, setApproving] = useState<string | null>(null);
  const [approveResult, setApproveResult] = useState<ApproveOut | null>(null);
  const [executing, setExecuting] = useState<ReconcileOut | null>(null);
  const [note, setNote] = useState<string>("");

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setLoadError(null);
    getProposal(id)
      .then((p) => {
        if (alive) setProposal(p);
      })
      .catch((e) => {
        if (alive) setLoadError(messageOf(e));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [id]);

  const status = proposal?.status;
  const proposalId = proposal?.proposal_id;

  useEffect(() => {
    if (isMockMode() || !proposalId || !status || !LIVE_STATUSES.includes(status)) return;
    const timer = window.setInterval(() => {
      getProposal(proposalId)
        .then((fresh) => setProposal(fresh))
        .catch(() => undefined);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [proposalId, status]);

  async function onApprove(alt: Alternative) {
    if (!proposal) return;
    setApproving(alt.type);
    setActionError(null);
    try {
      const out = await approveProposal(proposal.proposal_id, {
        alternative_type: alt.type,
        note: note || null,
      });
      setApproveResult(out);
      setProposal({ ...proposal, status: out.status });
    } catch (e) {
      
      setActionError(messageOf(e));
    } finally {
      setApproving(null);
    }
  }

  async function onReject() {
    if (!proposal) return;
    setActionError(null);
    try {
      await rejectProposal(proposal.proposal_id, { note: note || null });
      setProposal({ ...proposal, status: "REJECTED" });
    } catch (e) {
      setActionError(messageOf(e));
    }
  }

  async function onReconcile() {
    if (!proposal) return;
    setActionError(null);
    try {
      const out = await reconcileProposal(proposal.proposal_id);
      setExecuting(out);
      setProposal({ ...proposal, status: out.status });
    } catch (e) {
      setActionError(messageOf(e));
    }
  }

  async function onSandboxPay() {
    if (!proposal) return;
    setActionError(null);
    try {
      const out = await sandboxRecordPayment(proposal.proposal_id);
      setExecuting(out);
      setProposal({ ...proposal, status: out.status });
    } catch (e) {
      setActionError(messageOf(e));
    }
  }

  if (loading) return <div className="page loading">Loading proposal…</div>;
  if (loadError) return <div className="page error">{loadError}</div>;
  if (!proposal) return <div className="page">Proposal not found.</div>;

  const isBlocked = proposal.status === "BLOCKED";
  const canApprove = proposal.status === "PENDING_MERCHANT";
 
  const isPaid = proposal.status === "PAID" || executing?.status === "PAID";

  return (
    <div className="page" style={{ maxWidth: "1100px", margin: "0 auto" }}>
      {/* HEADER */}
      <header
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "24px",
          paddingBottom: "16px",
          borderBottom: "1px solid var(--border-subtle)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
          <h1 style={{ fontSize: "24px", fontWeight: 800, letterSpacing: "-0.5px", margin: 0 }}>
            Proposal Review
          </h1>
          <span className={`pill pill-${proposal.status.toLowerCase()}`}>{proposal.status}</span>
          <span
            className="muted"
            style={{ fontSize: "13px", borderLeft: "1px solid var(--border-subtle)", paddingLeft: "16px" }}
          >
            ID: <strong>{proposal.proposal_id}</strong> · Inv: <strong>{proposal.invoice_id}</strong>
          </span>
        </div>
        <div style={{ display: "flex", gap: "12px" }}>
          {proposal.status === "NEEDS_RECONCILIATION" && (
            <button className="btn btn-brand" onClick={onReconcile}>
              Refresh from PayPal
            </button>
          )}
          {proposal.status === "EXECUTED" && (
            <button className="btn btn-dark" onClick={onSandboxPay}>
              Record payment (Sandbox)
            </button>
          )}
        </div>
      </header>

      
      {actionError && (
        <div
          role="alert"
          style={{
            background: "#fef2f2",
            border: "1px solid #fecaca",
            color: "#991b1b",
            borderRadius: "12px",
            padding: "12px 16px",
            marginBottom: "16px",
            fontSize: "14px",
          }}
        >
          {actionError}
        </div>
      )}

      {isBlocked && <BlockedCard proposal={proposal} />}

      
      {!isBlocked && proposal.explanation && (
        <section
          style={{
            background: "var(--bg-app)",
            border: "1px solid var(--border-subtle)",
            borderRadius: "12px",
            padding: "20px",
            marginBottom: "24px",
            display: "flex",
            gap: "20px",
            alignItems: "flex-start",
          }}
        >
          <div style={{ fontSize: "24px" }}>✨</div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: "13px", fontWeight: 700, textTransform: "uppercase", color: "var(--text-tertiary)", marginBottom: "8px" }}>
              AI Explanation
            </div>
            <p style={{ fontSize: "14px", lineHeight: 1.5, color: "var(--text-primary)", margin: "0 0 12px 0" }}>
              {proposal.explanation}
            </p>
            {proposal.customer_message_draft && (
              <div style={{ fontSize: "13px", color: "var(--text-secondary)", fontStyle: "italic", borderLeft: "2px solid var(--brand-primary)", paddingLeft: "12px" }}>
                "{proposal.customer_message_draft}"
              </div>
            )}
          </div>
        </section>
      )}

      {/* COMPARADOR */}
      {!isBlocked && (
        <div style={{ marginBottom: "24px" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "20px" }}>
            {proposal.alternatives.map((alt) => (
              <AlternativeCard
                key={alt.type}
                alt={alt}
                disabled={!canApprove || !alt.policy_ok}
                busy={approving === alt.type}
                
                approved={approveResult?.approved_alternative === alt.type}
                
                locked={!!approveResult}
                onApprove={() => onApprove(alt)}
              />
            ))}
          </div>
        </div>
      )}

      {/* ACTIONS */}
      {canApprove && (
        <div style={{ display: "flex", gap: "16px", alignItems: "center", background: "var(--bg-surface)", border: "1px solid var(--border-subtle)", padding: "16px", borderRadius: "12px" }}>
          <input
            value={note}
            maxLength={200}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Optional merchant note..."
            style={{ flex: 1, padding: "10px 14px", borderRadius: "8px", border: "1px solid var(--border-subtle)", fontSize: "14px" }}
          />
          <button className="btn btn-danger" onClick={onReject} style={{ padding: "10px 20px", fontSize: "14px" }}>
            Reject
          </button>
        </div>
      )}

      {/* RESULT */}
      {approveResult && (
        <section style={{ marginTop: "24px", background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: "12px", padding: "20px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <h2 style={{ fontSize: "18px", fontWeight: 800, color: "#166534", margin: "0 0 4px 0" }}>
              ✔ Proposal Approved
            </h2>
            <p style={{ color: "#15803d", fontSize: "14px", margin: 0 }}>
              The one-time customer link has been generated successfully.
            </p>
          </div>
          
          <a
            className="btn btn-dark"
            style={{ padding: "12px 24px", textDecoration: "none", display: "inline-block" }}
            href={`/customer/${tokenFrom(approveResult.customer_link)}`}
            target="_blank"
            rel="noopener noreferrer"
          >
            Open Customer View →
          </a>
        </section>
      )}

      
      {isPaid && (
        <section className="card success" style={{ marginTop: "24px", padding: "20px" }}>
          <h2 style={{ fontSize: "18px", margin: 0 }}>Payment Confirmed</h2>
        </section>
      )}
    </div>
  );
}

function AlternativeCard({
  alt,
  onApprove,
  disabled,
  busy,
  approved,
  locked,
}: {
  alt: Alternative;
  onApprove: () => void;
  disabled: boolean;
  busy: boolean;
  approved: boolean;
  locked: boolean;
}) {
  const isPositiveDelta = !alt.merchant_difference_vs_balance.startsWith("-");
  
  const inactive = disabled || busy || locked;

  return (
    <article
      style={{
        background: "var(--bg-surface)",
        
        border: approved ? "2px solid var(--status-success)" : "1px solid var(--border-subtle)",
        borderRadius: "16px",
        padding: "24px",
        display: "flex",
        flexDirection: "column",
        height: "100%",
        
        opacity: locked && !approved ? 0.55 : 1,
      }}
    >
      <div style={{ marginBottom: "16px", fontSize: "16px", fontWeight: 700, color: "var(--text-primary)" }}>
        {ALT_LABEL[alt.type] ?? alt.type}
      </div>

      <div style={{ marginBottom: "20px" }}>
        <div style={{ fontSize: "36px", fontWeight: 800, color: "var(--text-primary)", letterSpacing: "-1.5px", lineHeight: 1 }}>
          {formatMoney(alt.amount_due_now)}
        </div>
        <div style={{ fontSize: "12px", fontWeight: 600, color: "var(--text-tertiary)", marginTop: "4px" }}>
          DUE TODAY
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "10px", marginBottom: "24px", flex: 1 }}>
        <div style={rowStyle}>
          <span style={labelStyle}>Installment</span>
          <span style={{ fontWeight: 600 }}>
            {alt.installment_amount ? formatMoney(alt.installment_amount) : "—"}
          </span>
        </div>
        <div style={rowStyle}>
          <span style={labelStyle}>Total Paid</span>
          <span style={{ fontWeight: 600 }}>{formatMoney(alt.total_paid)}</span>
        </div>
        <div style={rowStyle}>
          <span style={labelStyle}>Financing</span>
          <span style={{ fontWeight: 600 }}>{formatMoney(alt.financing_cost)}</span>
        </div>
        <div style={{ ...rowStyle, borderTop: "1px dashed var(--border-subtle)", paddingTop: "10px" }}>
          <span style={labelStyle}>Merchant Impact</span>
          <span style={{ fontWeight: 700, color: isPositiveDelta ? "var(--status-success)" : "var(--status-danger)" }}>
            {formatMoney(alt.merchant_difference_vs_balance)}
          </span>
        </div>
      </div>

      <button
        onClick={onApprove}
        disabled={inactive}
        style={{
          width: "100%",
          padding: "12px",
          borderRadius: "8px",
          fontSize: "15px",
          fontWeight: 700,
          border: "none",
          cursor: inactive ? "not-allowed" : "pointer",
          
          background: approved ? "var(--status-success)" : "var(--text-primary)",
          color: "white",
        }}
      >
        {approved ? "✔ Approved" : busy ? "Processing…" : "Approve Option"}
      </button>
    </article>
  );
}

function BlockedCard({ proposal }: { proposal: ProposalOut }) {
  const reason = proposal.blocked_reasons?.[0];
  const notice = reason ? AGENT_NOTICE[reason.code] : undefined;
  const showRule = !notice && !!reason && !!reason.limit && reason.limit !== "—";
  const text =
    notice?.text ?? reason?.message ?? "The proposal was blocked before it could be offered to the customer.";

  return (
    <section style={{ background: "#fef2f2", border: "1px solid #fecaca", borderRadius: "12px", padding: "24px", marginBottom: "24px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "12px" }}>
        <span style={{ fontSize: "24px" }}>{notice?.icon ?? "🚫"}</span>
        <h2 style={{ fontSize: "20px", fontWeight: 800, color: "#991b1b", margin: 0 }}>
          {notice?.title ?? "Blocked by guardrail"}
        </h2>
      </div>
      <p style={{ color: "#991b1b", fontSize: "14px", marginBottom: "16px" }}>{text}</p>
      {!proposal.paypal_called && (
        <p style={{ color: "#991b1b", fontSize: "14px", fontWeight: 600, marginBottom: "16px" }}>
          No PayPal actions were taken.
        </p>
      )}

      {showRule && reason && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "16px", background: "white", padding: "16px", borderRadius: "8px" }}>
          <div>
            <div style={{ fontSize: "11px", fontWeight: 600, color: "var(--text-tertiary)", textTransform: "uppercase" }}>Rule</div>
            <div style={{ fontSize: "15px", fontWeight: 700, color: "var(--text-primary)" }}>{reason.code}</div>
          </div>
          <div>
            <div style={{ fontSize: "11px", fontWeight: 600, color: "var(--text-tertiary)", textTransform: "uppercase" }}>Limit</div>
            <div style={{ fontSize: "15px", fontWeight: 700, color: "var(--text-primary)" }}>
              {reason.limit}{unitSuffix(reason.unit)}
            </div>
          </div>
          <div>
            <div style={{ fontSize: "11px", fontWeight: 600, color: "var(--text-tertiary)", textTransform: "uppercase" }}>Attempted</div>
            <div style={{ fontSize: "15px", fontWeight: 700, color: "var(--status-danger)" }}>
              {reason.attempted}{unitSuffix(reason.unit)}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}