import type { ColDef } from "ag-grid-community";
import type { AuditEvent } from "../types/api";
import { ActionBadge, SeverityPill, PaypalCalled } from "./cellRenderers";

export const auditColumns: ColDef<AuditEvent>[] = [
  { 
    field: "seq", headerName: "SEQ", width: 70, sort: "desc", pinned: "left", lockPosition: true,
    cellStyle: { color: 'var(--text-tertiary)', fontSize: '12px', fontWeight: 500 }
  },
  { field: "ts", headerName: "TIMESTAMP", width: 160, cellStyle: { color: 'var(--text-secondary)', fontSize: '13px' } },
  { 
    field: "severity", headerName: "SEVERITY", width: 120, cellRenderer: SeverityPill,
    cellStyle: { display: 'flex', alignItems: 'center', background: 'transparent', boxShadow: 'none', padding: '0 16px' } 
  },
  { field: "action", headerName: "ACTION", width: 240, cellRenderer: ActionBadge },
  {
    headerName: "STATE TRANSITION", width: 250,
    valueGetter: (p) => `${p.data?.state_from ?? "—"} → ${p.data?.state_to ?? "—"}`,
    cellStyle: { color: 'var(--text-secondary)', fontSize: '13px', fontFamily: 'monospace' }
  },
  
  { field: "actor.type", headerName: "ACTOR", width: 110 },
  { field: "rule.code", headerName: "RULE", width: 180 },
  { field: "rule.limit", headerName: "LIMIT", width: 90 },
  { field: "rule.attempted", headerName: "ATTEMPTED", width: 110 },
  
  { field: "paypal_called", headerName: "PAYPAL API?", width: 120, cellRenderer: PaypalCalled },
  { 
    field: "summary", headerName: "EVENT SUMMARY", flex: 1, minWidth: 350,
    cellStyle: { color: 'var(--text-primary)', fontSize: '13px', lineHeight: '1.4', whiteSpace: 'normal', display: 'flex', alignItems: 'center' }
  },
  {
    headerName: "", width: 100, pinned: "right",
    cellRenderer: (params: any) => {
      if (!params.data.proposal_id) return null;
      return (
        <button style={{ background: 'var(--bg-app)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)', padding: '6px 12px', borderRadius: '8px', cursor: 'pointer', fontSize: '12px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '6px', transition: 'all 0.2s', boxShadow: '0 1px 2px rgba(0,0,0,0.05)' }}
          onMouseOver={(e) => { e.currentTarget.style.background = 'var(--brand-primary)'; e.currentTarget.style.color = 'white'; e.currentTarget.style.borderColor = 'var(--brand-primary)'; }}
          onMouseOut={(e) => { e.currentTarget.style.background = 'var(--bg-app)'; e.currentTarget.style.color = 'var(--text-primary)'; e.currentTarget.style.borderColor = 'var(--border-subtle)'; }}
          onClick={() => { window.location.href = `/app/proposal/${params.data.proposal_id}`; }}
        >
          View <span style={{ fontSize: '14px' }}>→</span>
        </button>
      );
    }
  }
];