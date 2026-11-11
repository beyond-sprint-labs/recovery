import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { getCustomerProposal, respondAsCustomer } from "../api/client";
import type { CustomerProposalView, RespondOut } from "../types/api";
import { formatMoney } from "../components/Money";
import { SecurePlaceholder } from "../components/SecurePlaceholder";

export function CustomerPage() {
  const { token = "" } = useParams<{ token: string }>();
  const [view, setView] = useState<CustomerProposalView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [responded, setResponded] = useState<RespondOut | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getCustomerProposal(token)
      .then(setView)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [token]);

  async function respond(decision: "ACCEPT" | "DECLINE") {
    if (busy || responded) return; 
    
    setBusy(true);
    setError(null);
    
    try {
      const out = await respondAsCustomer(token, { decision });
      setResponded(out); 
    } catch (e: any) {
      if (e.message && (e.message.includes("409") || e.message.includes("Conflict"))) {
        setError("This link has already been used or has expired. Please contact the merchant for a new proposal.");
      } else {
        setError(e.message || "An unexpected error occurred.");
      }
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <div className="page loading">Loading…</div>;

  if (error) {
    return (
      <div style={{ minHeight: '100vh', background: 'var(--bg-app)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <SecurePlaceholder 
          title="Link Unavailable"
          description={error}
          actionLabel="Return to Home"
          onAction={() => window.location.href = '/'}
        />
      </div>
    );
  }
   
  if (!view) return <div className="page">Link not found.</div>;

  if (responded) {
    const isAccepted = responded.status === "ACCEPTED" || responded.status === "EXECUTED" || responded.status === "PAID";
    const isDeclined = responded.status === "DECLINED";
    const isPaid = responded.status === "PAID";

    return (
      <div className="customer-portal-wrapper">
        <div className="card" style={{ 
          border: isAccepted ? '1px solid var(--status-success)' : '1px solid var(--border-subtle)', 
          textAlign: 'center' 
        }}>
          <div style={{ fontSize: '48px', marginBottom: '16px', color: isAccepted ? 'var(--status-success)' : 'inherit' }}>
            {isPaid ? "✅" : isAccepted ? "📨" : isDeclined ? "🚫" : "⏳"}
          </div>
          
          <h1 style={{ fontSize: '24px', marginBottom: '8px' }}>
            {isPaid ? "Payment Confirmed!" : isAccepted ? "Repayment Plan Activated!" : isDeclined ? "Offer Declined" : "Processing..."}
          </h1>
          
          <p className="muted" style={{ marginBottom: '32px' }}>
            {isPaid 
              ? "Your payment has been confirmed. Thank you."
              : isAccepted 
              ? "Your new invoice has been sent through PayPal. Payment is not confirmed yet."
              : isDeclined 
              ? "You have declined the repayment offer. The merchant will be notified."
              : "We are finalizing your request with PayPal. Please wait."}
          </p>
          
          {isAccepted && (
            <div style={{ textAlign: 'left', background: 'var(--bg-app)', padding: '24px', borderRadius: 'var(--radius-sm)', marginBottom: '32px' }}>
              <h3 style={{ fontSize: '15px', fontWeight: 600, marginBottom: '20px', color: 'var(--text-primary)' }}>PayPal Sandbox Orchestration Details:</h3>
              
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '14px', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '12px' }}>
                  <span className="muted">Original Invoice:</span>
                  <span style={{ fontWeight: 600, color: 'var(--text-tertiary)', textDecoration: 'line-through' }}>
                    {responded.paypal?.original_invoice_id || "N/A"} (Cancelled)
                  </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '14px', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '12px' }}>
                  <span className="muted">Replacement Invoice:</span>
                  <span style={{ fontWeight: 600, color: 'var(--status-success)' }}>
                    {responded.paypal?.new_invoice_id || "N/A"} (Active)
                  </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '14px', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '12px' }}>
                  <span className="muted">Initial Due Today:</span>
                  <span style={{ fontWeight: 600 }}>{formatMoney(view.alternative.amount_due_now)} USD</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '14px' }}>
                  <span className="muted">Payment Status:</span>
                  {isPaid ? (
                    <span className="pill pill-approved" style={{ fontSize: '11px', padding: '2px 8px' }}>CONFIRMED</span>
                  ) : (
                    <span className="pill" style={{ fontSize: '11px', padding: '2px 8px', background: '#fef3c7', color: '#92400e' }}>AWAITING PAYMENT (Invoice Sent)</span>
                  )}
                </div>
              </div>
            </div>
          )}

          <button 
            className="btn" 
            style={{ width: '100%', padding: '14px' }}
            onClick={() => window.location.href = '/'}
          >
            Return to Home
          </button>
          
          <p className="muted" style={{ fontSize: '12px', marginTop: '24px' }}>
            {view.simulation_notice}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="customer-portal-wrapper">
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
          <div>
            <h2 style={{ fontSize: '20px', margin: 0 }}>DueGuide Portal</h2>
            <span className="muted" style={{ fontSize: '13px' }}>Pre-approved offer</span>
          </div>
          <span className="pill pill-approved">Pre-Approved</span>
        </div>

        <blockquote className="customer-message">{view.customer_message}</blockquote>

        <div className="kv-list" style={{ background: 'var(--bg-app)', padding: '20px', borderRadius: '8px' }}>
          <div className="kv-item" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
            <span className="kv-label">Outstanding Balance</span>
            <span className="kv-value" style={{ color: 'var(--text-primary)' }}>{formatMoney(view.original_balance)}</span>
          </div>
          <div className="kv-item" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
            <span className="kv-label">Pay Now (Due Today)</span>
            <span className="kv-value positive">{formatMoney(view.alternative.amount_due_now)}</span>
          </div>
          <div className="kv-item" style={{ borderBottom: 'none' }}>
            <span className="kv-label">Total Payment</span>
            <span className="kv-value">{formatMoney(view.alternative.total_paid)}</span>
          </div>
        </div>

        <div style={{ marginTop: '24px' }}>
          <h3 style={{ fontSize: '14px', fontWeight: 700, marginBottom: '12px' }}>Payment Schedule</h3>
          <table className="schedule">
            <thead>
              <tr>
                <th>Installment</th>
                <th>Due Date</th>
                <th style={{ textAlign: 'right' }}>Amount</th>
              </tr>
            </thead>
            <tbody>
              {view.alternative.schedule.map((s, i) => (
                <tr key={s.n}>
                  <td>{i === 0 ? "Down Payment" : `Installment #${s.n}`}</td>
                  <td>{s.due_date}</td>
                  <td style={{ textAlign: 'right' }}>{formatMoney(s.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="row" style={{ marginTop: '32px', display: 'flex', gap: '12px' }}>
          <button className="btn btn-dark" style={{ flex: 1, padding: '16px' }} disabled={busy} onClick={() => respond("ACCEPT")}>
            {busy ? "Processing…" : "Accept Repayment Plan"}
          </button>
          <button className="btn btn-danger" style={{ flex: 1, padding: '16px' }} disabled={busy} onClick={() => respond("DECLINE")}>
            Decline Offer
          </button>
        </div>

        <p className="muted" style={{ fontSize: '12px', textAlign: 'center', marginTop: '24px' }}>
          Simulation: this is a demo running on PayPal Sandbox. No real money is charged.
        </p>
      </div>
    </div>
  );
}