import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AgGridReact } from "ag-grid-react";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { getInvoices, createProposal } from "../api/client";
import type { Invoice } from "../types/api";
import { invoiceColumns } from "../grid/invoiceColumns";
import { formatMoney } from "../components/Money";

export function InvoicesPage() {
  const [rows, setRows] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [proposing, setProposing] = useState<string | null>(null);
  const [scenario, setScenario] = useState<string>("");
  const [message, setMessage] = useState<string>("I can pay part now, can we work something out?");
  const navigate = useNavigate();

  useEffect(() => {
    getInvoices()
      .then(setRows)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  const columns = useMemo<ColDef<Invoice>[]>(
    () => [
      ...invoiceColumns,
      {
        headerName: "Action",
        width: 140,
        pinned: "right",
        cellRenderer: (p: ICellRendererParams<Invoice>) => {
          const isOverdue = p.data?.status === "OVERDUE";
          const busy = proposing === p.data?.id;
          return (
            <button
              className="btn btn-primary"
              disabled={!isOverdue || busy || !p.data}
              onClick={() => p.data && onPropose(p.data)}
            >
              {busy ? "…" : "Propose"}
            </button>
          );
        },
      },
    ],
    
    [proposing, scenario, message],
  );

  async function onPropose(invoice: Invoice) {
    setProposing(invoice.id);
    setError(null);
    try {
      const proposal = await createProposal(invoice.id, {
        customer_message: message,
        scenario_id: scenario || null,
      });
      navigate(`/app/proposal/${proposal.proposal_id}`);
    } catch (e) {
      setError(String(e));
    } finally {
      setProposing(null);
    }
  }

  return (
    <div className="page">
      <h1>Overview</h1>
      
      <div className="info-banner">
        <div className="info-banner-icon">✨</div>
        <div>
          <h2>AI Recommendation available</h2>
          <p>We detected overdue invoices. The AI has analyzed customer intent and can generate tailored payment alternatives.</p>
        </div>
      </div>

      <p className="muted" style={{ marginBottom: '24px' }}>
        Select an overdue invoice and click <em>Propose</em> to start the intelligent negotiation.
      </p>

      <div className="controls">
        <label>
          Customer message
          <input
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            maxLength={500}
            placeholder="e.g. Can I get 40% off if I pay this week?"
          />
        </label>
        <label>
          Scenario (demo)
          <select value={scenario} onChange={(e) => setScenario(e.target.value)}>
            <option value="S01_partial_payment_now">S01 · Partial payment (SUCCESS)</option>
            <option value="S02_reasonable_discount">S02 · Reasonable discount (SUCCESS)</option>
            <option value="S03_exceeds_discount">S03 · Exceeds discount (BLOCKED)</option>
            <option value="S11_text_mismatch">S11 · Text/number mismatch (BLOCKED)</option>
          </select>
        </label>
      </div>

      {error ? <div className="error" style={{ color: 'red', marginBottom: '16px' }}>{error}</div> : null}

      {/* DESKTOP VIEW: AG Grid*/}
      <div className="desktop-grid grid-wrapper ag-theme-quartz" style={{ height: 480 }}>
        {loading ? (
          <div className="loading">Loading invoices…</div>
        ) : (
          <AgGridReact<Invoice>
            rowData={rows}
            columnDefs={columns}
            defaultColDef={{ sortable: true, filter: true, resizable: true }}
            getRowId={(p) => p.data.id}

            pagination={true}
            paginationPageSize={10}
            paginationPageSizeSelector={[10, 20, 50]}
          />
        )}
      </div>

      {/* MOBILE VIEW: Cards */}
      <div className="mobile-invoice-list">
        {loading && <div className="loading">Loading invoices…</div>}
        {!loading && rows.map(inv => (
          <div key={inv.id} className="mobile-card">
            <div className="mobile-card-header">
              <span className="mobile-card-title">{inv.customer_name}</span>
              <span className={`pill ${inv.status === 'OVERDUE' ? 'pill-blocked' : 'pill-paid'}`} style={{ fontSize: '10px' }}>
                {inv.status}
              </span>
            </div>
            <div className="mobile-card-row">
              <span>Invoice</span>
              <span style={{ fontWeight: 600 }}>{inv.id}</span>
            </div>
            <div className="mobile-card-row">
              <span>Balance</span>
              <span style={{ fontWeight: 600 }}>{formatMoney(inv.balance)}</span>
            </div>
            <div className="mobile-card-row">
              <span>Due date</span>
              <span>{inv.due_date}</span>
            </div>
            <button
              className="btn btn-primary"
              style={{ width: '100%', marginTop: '8px' }}
              disabled={inv.status !== 'OVERDUE' || proposing === inv.id}
              onClick={() => onPropose(inv)}
            >
              {proposing === inv.id ? "Processing…" : "Propose Settlement"}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}