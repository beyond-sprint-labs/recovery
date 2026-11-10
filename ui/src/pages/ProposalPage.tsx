import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  approveProposal,
  getProposal,
  reconcileProposal,
  rejectProposal,
  sandboxRecordPayment,
} from "../api/client";
import type {
  Alternative,
  ApproveOut,
  ProposalOut,
  ReconcileOut,
} from "../types/api";
import { formatMoney } from "../components/Money";

const ALT_LABEL: Record<string, string> = {
  settlement_discount: "Settlement Discount",
  down_payment_installments: "Down Payment + Installments",
};

export function ProposalPage() {
  const { id = "" } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [proposal, setProposal] = useState<ProposalOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [approving, setApproving] = useState<string | null>(null);
  const [approveResult, setApproveResult] = useState<ApproveOut | null>(null);
  const [executing, setExecuting] = useState<ReconcileOut | null>(null);
  const [note, setNote] = useState<string>("");

  useEffect(() => {
    setLoading(true);
    getProposal(id)
      .then(setProposal)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [id]);

  async function onApprove(alt: Alternative) {
    if (!proposal) return;
    setApproving(alt.type);
    setError(null);
    try {
      const out = await approveProposal(proposal.proposal_id, {
        alternative_type: alt.type,
        note: note || null,
      });
      

      setApproveResult(out);
      setProposal({ ...proposal, status: out.status });
    } catch (e) {
      setError(String(e));
    } finally {
      setApproving(null);
    }
  }

  async function onReject() {
    if (!proposal) return;
    try {
      await rejectProposal(proposal.proposal_id, { note: note || null });
      setProposal({ ...proposal, status: "REJECTED" });
    } catch (e) {
      setError(String(e));
    }
  }

  async function onReconcile() {
    if (!proposal) return;
    setError(null);
    try {
      const out = await reconcileProposal(proposal.proposal_id);
      setExecuting(out);
      setProposal({ ...proposal, status: out.status });
    } catch (e: any) {
      setError(e.message || "Failed to reconcile with PayPal.");
    }
  }

  async function onSandboxPay() {
    if (!proposal) return;
    setError(null);
    try {
      const out = await sandboxRecordPayment(proposal.proposal_id);
      setExecuting(out);
      setProposal({ ...proposal, status: out.status });
    } catch (e: any) {
      setError(e.message || "Failed to record Sandbox payment.");
    }
  }

  if (loading) return <div className="page loading">Loading proposal…</div>;
  if (error) return <div className="page error">{error}</div>;
  if (!proposal) return <div className="page">Proposal not found.</div>;

  const isBlocked = proposal.status === "BLOCKED";
  const canApprove = proposal.status === "PENDING_MERCHANT";

  return (
    <div className="page" style={{ maxWidth: '1100px', margin: '0 auto' }}>
      
      {/* HEADER */}
      <header style={{ 
        display: 'flex', justifyContent: 'space-between', alignItems: 'center', 
        marginBottom: '24px', paddingBottom: '16px', borderBottom: '1px solid var(--border-subtle)'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <h1 style={{ fontSize: '24px', fontWeight: 800, letterSpacing: '-0.5px', margin: 0 }}>
            Proposal Review
          </h1>
          <span className={`pill pill-${proposal.status.toLowerCase()}`}>{proposal.status}</span>
          <span className="muted" style={{ fontSize: '13px', borderLeft: '1px solid var(--border-subtle)', paddingLeft: '16px' }}>
            ID: <strong>{proposal.proposal_id}</strong> · Inv: <strong>{proposal.invoice_id}</strong>
          </span>
        </div>
        
        <div style={{ display: 'flex', gap: '12px' }}>
          {proposal.status === "NEEDS_RECONCILIATION" && (
            <button className="btn btn-brand" onClick={onReconcile}>Refresh from PayPal</button>
          )}
          {proposal.status === "EXECUTED" && (
            <button className="btn btn-dark" onClick={onSandboxPay}>Record payment (Sandbox)</button>
          )}
        </div>
      </header>

      {isBlocked && <BlockedCard proposal={proposal} />}

      {/* EXPLANATION */}
      {!isBlocked && proposal.explanation && (
        <section style={{ 
          background: 'var(--bg-app)', border: '1px solid var(--border-subtle)', 
          borderRadius: '12px', padding: '20px', marginBottom: '24px',
          display: 'flex', gap: '20px', alignItems: 'flex-start'
        }}>
          <div style={{ fontSize: '24px' }}>✨</div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: '13px', fontWeight: 700, textTransform: 'uppercase', color: 'var(--text-tertiary)', marginBottom: '8px' }}>AI Explanation</div>
            <p style={{ fontSize: '14px', lineHeight: 1.5, color: 'var(--text-primary)', margin: '0 0 12px 0' }}>
              {proposal.explanation}
            </p>
            {proposal.customer_message_draft && (
              <div style={{ fontSize: '13px', color: 'var(--text-secondary)', fontStyle: 'italic', borderLeft: '2px solid var(--brand-primary)', paddingLeft: '12px' }}>
                "{proposal.customer_message_draft}"
              </div>
            )}
          </div>
        </section>
      )}

      {/* COMPARATOR */}
      {!isBlocked && (
        <div style={{ marginBottom: '24px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
            {proposal.alternatives.map((alt, index) => (
              <AlternativeCard
                key={alt.type}
                alt={alt}
                isRecommended={index === 1}
                disabled={!canApprove || !alt.policy_ok}
                busy={approving === alt.type}
                onApprove={() => onApprove(alt)}
                alreadyApproved={!!approveResult}
              />
            ))}
          </div>
        </div>
      )}

      {/* ACTIONS */}
      {canApprove && (
        <div style={{ display: 'flex', gap: '16px', alignItems: 'center', background: 'var(--bg-surface)', border: '1px solid var(--border-subtle)', padding: '16px', borderRadius: '12px' }}>
          <input
            value={note}
            maxLength={200}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Optional merchant note..."
            style={{ flex: 1, padding: '10px 14px', borderRadius: '8px', border: '1px solid var(--border-subtle)', fontSize: '14px' }}
          />
          <button className="btn btn-danger" onClick={onReject} style={{ padding: '10px 20px', fontSize: '14px' }}>
            Reject
          </button>
        </div>
      )}

      {/* RESULT */}
      {approveResult && (
        <section style={{ 
          marginTop: '24px', background: '#f0fdf4', border: '1px solid #bbf7d0', 
          borderRadius: '12px', padding: '20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center'
        }}>
          <div>
            <h2 style={{ fontSize: '18px', fontWeight: 800, color: '#166534', margin: '0 0 4px 0' }}>
              ✔ Proposal Approved
            </h2>
            <p style={{ color: '#15803d', fontSize: '14px', margin: 0 }}>
              The one-time customer link has been generated successfully.
            </p>
          </div>
          <button
            className="btn btn-dark"
            style={{ padding: '12px 24px' }}
            onClick={() => {
              const token = approveResult.customer_link.split("/").pop() ?? "";
              navigate(`/customer/${token}`);
            }}
          >
            Open Customer View →
          </button>
        </section>
      )}

      {executing?.status === "PAID" && (
        <section className="card success" style={{ marginTop: '24px', padding: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: 0 }}>Payment Confirmed via PayPal</h2>
        </section>
      )}
    </div>
  );
}

// --- COMPACT CARD ---
function AlternativeCard({
  alt,
  onApprove,
  disabled,
  busy,
  isRecommended,
  alreadyApproved
}: {
  alt: Alternative;
  onApprove: () => void;
  disabled: boolean;
  busy: boolean;
  isRecommended?: boolean;
  alreadyApproved?: boolean;
}) {
  const isPositiveDelta = !alt.merchant_difference_vs_balance.startsWith("-");

  return (
    <article style={{
      background: 'var(--bg-surface)',
      border: isRecommended ? '2px solid var(--brand-primary)' : '1px solid var(--border-subtle)',
      borderRadius: '16px',
      padding: '24px', 
      position: 'relative',
      display: 'flex',
      flexDirection: 'column',
      boxShadow: isRecommended ? '0 10px 20px -5px rgba(0,112,186,0.1)' : 'none',
      height: '100%'
    }}>
      
      {isRecommended && (
        <div style={{
          position: 'absolute', top: '-12px', left: '24px',
          background: 'var(--brand-primary)', color: 'white',
          padding: '4px 12px', borderRadius: '100px',
          fontSize: '11px', fontWeight: 800, letterSpacing: '0.5px',
        }}>
          ⭐ RECOMMENDED
        </div>
      )}

      <div style={{ marginBottom: '16px' }}>
        <div style={{ fontSize: '16px', fontWeight: 700, color: 'var(--text-primary)' }}>
          {ALT_LABEL[alt.type] ?? alt.type}
        </div>
      </div>
      
      <div style={{ marginBottom: '20px' }}>
        <div style={{ fontSize: '36px', fontWeight: 800, color: 'var(--text-primary)', letterSpacing: '-1.5px', lineHeight: 1 }}>
          {formatMoney(alt.amount_due_now)}
        </div>
        <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-tertiary)', marginTop: '4px' }}>
          DUE TODAY
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginBottom: '24px', flex: 1 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px' }}>
          <span style={{ color: 'var(--text-secondary)' }}>Installment</span>
          <span style={{ fontWeight: 600 }}>{alt.installment_amount ? formatMoney(alt.installment_amount) : "—"}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px' }}>
          <span style={{ color: 'var(--text-secondary)' }}>Total Paid</span>
          <span style={{ fontWeight: 600 }}>{formatMoney(alt.total_paid)}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px' }}>
          <span style={{ color: 'var(--text-secondary)' }}>Financing</span>
          <span style={{ fontWeight: 600 }}>{formatMoney(alt.financing_cost)}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px', borderTop: '1px dashed var(--border-subtle)', paddingTop: '10px' }}>
          <span style={{ color: 'var(--text-secondary)' }}>Merchant Impact</span>
          <span style={{ fontWeight: 700, color: isPositiveDelta ? 'var(--status-success)' : 'var(--status-danger)' }}>
            {formatMoney(alt.merchant_difference_vs_balance)}
          </span>
        </div>
      </div>

      <button 
        onClick={onApprove}
        disabled={disabled || busy || alreadyApproved}
        style={{ 
          width: '100%', padding: '12px', borderRadius: '8px', 
          fontSize: '15px', fontWeight: 700, border: 'none', 
          cursor: (disabled || busy || alreadyApproved) ? 'not-allowed' : 'pointer',
          background: alreadyApproved ? 'var(--status-success)' : (isRecommended ? 'var(--brand-primary)' : 'var(--text-primary)'),
          color: 'white',
          transition: 'all 0.2s',
        }}
      >
        {alreadyApproved ? "✔ Approved" : busy ? "Processing…" : "Approve Option"}
      </button>
    </article>
  );
}

function BlockedCard({ proposal }: { proposal: ProposalOut }) {
  return (
    <section style={{ 
      background: '#fef2f2', border: '1px solid #fecaca', borderRadius: '12px', 
      padding: '24px', marginBottom: '24px' 
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '12px' }}>
        <span style={{ fontSize: '24px' }}>🚫</span>
        <h2 style={{ fontSize: '20px', fontWeight: 800, color: '#991b1b', margin: 0 }}>Blocked by AI Guardrail</h2>
      </div>
      <p style={{ color: '#991b1b', fontSize: '14px', marginBottom: '16px' }}>
        The AI attempted to generate terms that violate your financial policy. No PayPal actions were taken.
      </p>
      
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px', background: 'white', padding: '16px', borderRadius: '8px' }}>
        <div>
          <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-tertiary)', textTransform: 'uppercase' }}>Rule</div>
          <div style={{ fontSize: '15px', fontWeight: 700, color: 'var(--text-primary)' }}>{proposal.blocked_reasons?.[0]?.code}</div>
        </div>
        <div>
          <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-tertiary)', textTransform: 'uppercase' }}>Limit</div>
          <div style={{ fontSize: '15px', fontWeight: 700, color: 'var(--text-primary)' }}>{proposal.blocked_reasons?.[0]?.limit}%</div>
        </div>
        <div>
          <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-tertiary)', textTransform: 'uppercase' }}>Attempted</div>
          <div style={{ fontSize: '15px', fontWeight: 700, color: 'var(--status-danger)' }}>{proposal.blocked_reasons?.[0]?.attempted}%</div>
        </div>
      </div>
    </section>
  );
}