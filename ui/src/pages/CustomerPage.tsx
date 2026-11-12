import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { ApiRequestError, getCustomerProposal, respondAsCustomer } from "../api/client";
import type {
  AlternativeType,
  CustomerProposalView,
  ProposalStatus,
  RespondOut,
} from "../types/api";
import { formatMoney } from "../components/Money";
import { SecurePlaceholder } from "../components/SecurePlaceholder";

const TOKEN_ERRORS: Record<string, string> = {
  TOKEN_EXPIRED: "This link has expired. Please contact the merchant for a new proposal.",
  TOKEN_ALREADY_USED:
    "This link has already been used. Please contact the merchant if you need help.",
};

function isTokenError(e: unknown): e is ApiRequestError {
  return e instanceof ApiRequestError && e.code !== null && e.code in TOKEN_ERRORS;
}

function describe(e: unknown): string {
  if (isTokenError(e)) return TOKEN_ERRORS[e.code as string];
  return e instanceof Error ? e.message : "Unexpected error.";
}

interface Outcome {
  icon: string;
  title: string;
  text: string;
  showReceipt: boolean;
}

function outcomeFor(status: ProposalStatus, type: AlternativeType): Outcome {
  switch (status) {
    case "PAID":
      return type === "settlement_discount"
        ? {
            icon: "✅",
            title: "Payment confirmed",
            text: "Your payment has been confirmed. Thank you.",
            showReceipt: true,
          }
        : {
            icon: "✅",
            title: "First scheduled payment confirmed",
            text: "Your first scheduled payment has been confirmed. Thank you.",
            showReceipt: true,
          };
    case "EXECUTED":
      return {
        icon: "📨",
        title: "Repayment plan activated",
        text: "Your new invoice has been sent through PayPal. Payment is not confirmed yet.",
        showReceipt: true,
      };
    case "DECLINED":
      return {
        icon: "🚫",
        title: "Offer declined",
        text: "You have declined the offer. The merchant will be notified.",
        showReceipt: false,
      };
    case "FAILED":
      return {
        icon: "⚠️",
        title: "We could not activate your plan",
        text: "Something went wrong while creating the replacement invoice. Please contact the merchant.",
        showReceipt: false,
      };
    case "NEEDS_RECONCILIATION":
      return {
        icon: "⏳",
        title: "Verification in progress",
        text: "Your request was received, but we are still verifying it with PayPal. Please contact the merchant if you do not hear back.",
        showReceipt: false,
      };
    default:
      return {
        icon: "⏳",
        title: "Processing…",
        text: "We are finalizing your request. Please wait.",
        showReceipt: false,
      };
  }
}

function scheduleLabel(type: AlternativeType, n: number): string {
  if (type === "settlement_discount") return "Settlement payment";
  return n === 0 ? "Down payment" : `Installment #${n}`;
}

export function CustomerPage() {
  const { token = "" } = useParams<{ token: string }>();
  const [view, setView] = useState<CustomerProposalView | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [responded, setResponded] = useState<RespondOut | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    getCustomerProposal(token)
      .then((v) => {
        if (alive) setView(v);
      })
      .catch((e) => {
        if (alive) setLoadError(describe(e));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [token]);

  async function respond(decision: "ACCEPT" | "DECLINE") {
    if (busy || responded) return;
    setBusy(true);
    setActionError(null);
    try {
      const out = await respondAsCustomer(token, { decision });
      setResponded(out);
    } catch (e) {
      if (isTokenError(e)) setLoadError(describe(e));
      else setActionError(describe(e));
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <div className="page loading">Loading…</div>;

  if (loadError) {
    return (
      <div
        style={{
          minHeight: "100vh",
          background: "var(--bg-app)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <SecurePlaceholder
          title="Link unavailable"
          description={loadError}
          actionLabel="Return to Home"
          onAction={() => {
            window.location.href = "/";
          }}
        />
      </div>
    );
  }

  if (!view) return <div className="page">Link not found.</div>;

  const altType = view.alternative.type;

  if (responded) {
    const outcome = outcomeFor(responded.status, altType);
    const isPaid = responded.status === "PAID";

    return (
      <div className="customer-portal-wrapper">
        <div
          className="card"
          style={{
            border: outcome.showReceipt
              ? "1px solid var(--status-success)"
              : "1px solid var(--border-subtle)",
            textAlign: "center",
          }}
        >
          <div style={{ fontSize: "48px", marginBottom: "16px" }}>{outcome.icon}</div>
          <h1 style={{ fontSize: "24px", marginBottom: "8px" }}>{outcome.title}</h1>
          <p className="muted" style={{ marginBottom: "32px" }}>
            {outcome.text}
          </p>

          {outcome.showReceipt && (
            <div
              style={{
                textAlign: "left",
                background: "var(--bg-app)",
                padding: "24px",
                borderRadius: "var(--radius-sm)",
                marginBottom: "32px",
              }}
            >
              <h3
                style={{
                  fontSize: "15px",
                  fontWeight: 600,
                  marginBottom: "20px",
                  color: "var(--text-primary)",
                }}
              >
                PayPal Sandbox details
              </h3>
              <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    fontSize: "14px",
                    borderBottom: "1px solid var(--border-subtle)",
                    paddingBottom: "12px",
                  }}
                >
                  <span className="muted">Original invoice</span>
                  <span
                    style={{
                      fontWeight: 600,
                      color: "var(--text-tertiary)",
                      textDecoration: "line-through",
                    }}
                  >
                    {responded.paypal?.original_invoice_id ?? "N/A"} (cancelled)
                  </span>
                </div>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    fontSize: "14px",
                    borderBottom: "1px solid var(--border-subtle)",
                    paddingBottom: "12px",
                  }}
                >
                  <span className="muted">Replacement invoice</span>
                  <span style={{ fontWeight: 600, color: "var(--status-success)" }}>
                    {responded.paypal?.new_invoice_id ?? "N/A"} (active)
                  </span>
                </div>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    fontSize: "14px",
                    borderBottom: "1px solid var(--border-subtle)",
                    paddingBottom: "12px",
                  }}
                >
                  <span className="muted">Due today</span>
                  <span style={{ fontWeight: 600 }}>
                    {formatMoney(view.alternative.amount_due_now)} USD
                  </span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "14px" }}>
                  <span className="muted">Payment status</span>
                  {isPaid ? (
                    <span className="pill pill-approved" style={{ fontSize: "11px", padding: "2px 8px" }}>
                      {altType === "settlement_discount" ? "CONFIRMED" : "FIRST PAYMENT CONFIRMED"}
                    </span>
                  ) : (
                    <span
                      className="pill"
                      style={{
                        fontSize: "11px",
                        padding: "2px 8px",
                        background: "#fef3c7",
                        color: "#92400e",
                      }}
                    >
                      AWAITING PAYMENT (invoice sent)
                    </span>
                  )}
                </div>
              </div>
            </div>
          )}

          <button
            className="btn"
            style={{ width: "100%", padding: "14px" }}
            onClick={() => {
              window.location.href = "/";
            }}
          >
            Return to Home
          </button>
          
          <p
            className="muted"
            style={{
              fontSize: "12px",
              marginTop: "24px",
              lineHeight: 1.5,
              maxWidth: "420px",
              marginLeft: "auto",
              marginRight: "auto",
           }}
          >
              {view.simulation_notice}
            </p>
          </div>
        </div>
    );
  }

  return (
    <div className="customer-portal-wrapper">
      <div className="card">
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: "24px",
          }}
        >
          <div>
            <h2 style={{ fontSize: "20px", margin: 0 }}>DueGuide Portal</h2>
            <span className="muted" style={{ fontSize: "13px" }}>
              Pre-approved offer
            </span>
          </div>
          <span className="pill pill-approved">Pre-Approved</span>
        </div>

        <blockquote className="customer-message">{view.customer_message}</blockquote>

        <div
          className="kv-list"
          style={{ background: "var(--bg-app)", padding: "20px", borderRadius: "8px" }}
        >
          <div className="kv-item" style={{ borderBottom: "1px solid var(--border-subtle)" }}>
            <span className="kv-label">Outstanding balance</span>
            <span className="kv-value" style={{ color: "var(--text-primary)" }}>
              {formatMoney(view.original_balance)}
            </span>
          </div>
          <div className="kv-item" style={{ borderBottom: "1px solid var(--border-subtle)" }}>
            <span className="kv-label">Pay now (due today)</span>
            <span className="kv-value positive">{formatMoney(view.alternative.amount_due_now)}</span>
          </div>
          <div className="kv-item" style={{ borderBottom: "none" }}>
            <span className="kv-label">Total payment</span>
            <span className="kv-value">{formatMoney(view.alternative.total_paid)}</span>
          </div>
        </div>

        <div style={{ marginTop: "24px" }}>
          <h3 style={{ fontSize: "14px", fontWeight: 700, marginBottom: "12px" }}>
            Payment schedule
          </h3>
          <table className="schedule">
            <thead>
              <tr>
                <th>Payment</th>
                <th>Due date</th>
                <th style={{ textAlign: "right" }}>Amount</th>
              </tr>
            </thead>
            <tbody>
              {view.alternative.schedule.map((s) => (
                <tr key={s.n}>
                  <td>{scheduleLabel(altType, s.n)}</td>
                  <td>{s.due_date}</td>
                  <td style={{ textAlign: "right" }}>{formatMoney(s.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="row" style={{ marginTop: "32px", display: "flex", gap: "12px" }}>
          <button
            className="btn btn-dark"
            style={{ flex: 1, padding: "16px" }}
            disabled={busy}
            onClick={() => respond("ACCEPT")}
          >
            {busy ? "Processing…" : "Accept Offer"}
          </button>
          <button
            className="btn btn-danger"
            style={{ flex: 1, padding: "16px" }}
            disabled={busy}
            onClick={() => respond("DECLINE")}
          >
            Decline Offer
          </button>
        </div>

        {busy && (
          <p className="muted" style={{ fontSize: "13px", textAlign: "center", marginTop: "16px" }}>
            Processing your response. This can take a few seconds…
          </p>
        )}

        {actionError && (
          <p
            role="alert"
            style={{ color: "#991b1b", fontSize: "13px", textAlign: "center", marginTop: "16px" }}
          >
            {actionError}
          </p>
        )}

        <p
          className="muted"
          style={{
            fontSize: "12px",
            textAlign: "center",
            marginTop: "24px",
            lineHeight: 1.5,
            maxWidth: "420px",
            marginLeft: "auto",
            marginRight: "auto",
          }}
        >
          {view.simulation_notice}
        </p>
      </div>
    </div>
  );
}