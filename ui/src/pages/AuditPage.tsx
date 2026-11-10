import { useCallback, useEffect, useRef, useState } from "react";
import { AgGridReact } from "ag-grid-react";
import type { GridApi, GridReadyEvent, RowClassRules } from "ag-grid-community";
import { getAuditEvents } from "../api/client";
import type { AuditEvent } from "../types/api";
import { auditColumns } from "../grid/auditColumns";

const POLL_MS = 1500;

const rowClassRules: RowClassRules<AuditEvent> = {
  "row-critical": (p) => p.data?.severity === "CRITICAL",
  "row-warn": (p) => p.data?.severity === "WARN",
  "row-info": (p) => p.data?.severity === "INFO",
};

export function AuditPage() {
  const [rows, setRows] = useState<AuditEvent[]>([]);
  const [nextSeq, setNextSeq] = useState<number>(0);
  const [autoScroll, setAutoScroll] = useState(true);
  const [isPaused, setIsPaused] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const gridApiRef = useRef<GridApi<AuditEvent> | null>(null);
  const pollRef = useRef<number | null>(null);
  const aliveRef = useRef(true);

  const onGridReady = useCallback((e: GridReadyEvent<AuditEvent>) => {
    gridApiRef.current = e.api;
  }, []);

  const poll = useCallback(async () => {
    if (isPaused) return; 
    
    try {
      const page = await getAuditEvents(nextSeq);
      if (!aliveRef.current) return;
      if (page.items.length > 0) {
        setRows((prev) => [...prev, ...page.items]);
        setNextSeq(page.next_seq);
        gridApiRef.current?.applyTransaction({ add: page.items, addIndex: 0 });
        if (autoScroll) {
          const last = page.items[page.items.length - 1];
          const node = gridApiRef.current?.getRowNode(last.event_id);
          if (node) gridApiRef.current?.flashCells({ rowNodes: [node] });
        }
      }
    } catch (e) {
      setError(String(e));
    }
  }, [nextSeq, autoScroll, isPaused]);

  useEffect(() => {
    aliveRef.current = true;
    poll();
    pollRef.current = window.setInterval(poll, POLL_MS);
    return () => {
      aliveRef.current = false;
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
  }, [poll]);

  return (
    <div className="page">
      <header className="page-head" style={{ marginBottom: '32px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--brand-primary)', fontWeight: 600, fontSize: '12px', textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '8px' }}>
            <span>📊</span> Live Telemetry
          </div>
          <h1>Live Audit & Compliance Trail</h1>
          <p className="muted">
            Immutable AG Grid event stream monitoring financial guardrails, state transitions, and PayPal orchestration.
          </p>
        </div>
        
        {/* Stream Controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <label className="toggle" style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', fontWeight: 600, marginRight: '12px' }}>
            <input type="checkbox" checked={autoScroll} onChange={(e) => setAutoScroll(e.target.checked)} />
            Auto-scroll
          </label>
          
          <button 
            className="btn" 
            onClick={() => setIsPaused(!isPaused)}
            style={{ 
              background: isPaused ? 'var(--status-warning-bg)' : 'transparent', 
              color: isPaused ? 'var(--status-warning)' : 'inherit',
              border: isPaused ? '1px solid var(--status-warning)' : '1px solid var(--border-subtle)'
            }}
          >
            {isPaused ? "▶ Resume Stream" : "⏸ Pause Stream"}
          </button>
        </div>
      </header>

      {error ? <div className="error">{error}</div> : null}

      {/* KPI Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '20px', marginBottom: '32px' }}>
        <div className="card" style={{ padding: '24px' }}>
          <div className="muted" style={{ fontSize: '12px', textTransform: 'uppercase', letterSpacing: '0.5px', fontWeight: 600 }}>Total Events Streamed</div>
          <div style={{ fontSize: '36px', fontWeight: 800, marginTop: '8px', color: 'var(--text-primary)' }}>{rows.length}</div>
        </div>
        <div className="card" style={{ padding: '24px', borderLeft: '4px solid var(--status-danger)' }}>
          <div className="muted" style={{ fontSize: '12px', textTransform: 'uppercase', letterSpacing: '0.5px', fontWeight: 600, color: 'var(--status-danger)' }}>Critical Interceptions</div>
          <div style={{ fontSize: '36px', fontWeight: 800, marginTop: '8px', color: 'var(--status-danger)' }}>
            {rows.filter(r => r.severity === "CRITICAL").length}
          </div>
        </div>
        <div className="card" style={{ padding: '24px' }}>
          <div className="muted" style={{ fontSize: '12px', textTransform: 'uppercase', letterSpacing: '0.5px', fontWeight: 600 }}>Stream Frequency</div>
          <div style={{ fontSize: '36px', fontWeight: 800, marginTop: '8px', color: 'var(--text-primary)' }}>~1.5s</div>
        </div>
        <div className="card" style={{ padding: '24px' }}>
          <div className="muted" style={{ fontSize: '12px', textTransform: 'uppercase', letterSpacing: '0.5px', fontWeight: 600 }}>License Mode</div>
          <div style={{ fontSize: '18px', fontWeight: 700, marginTop: '16px', color: 'var(--text-primary)' }}>AG Grid Community</div>
        </div>
      </div>
      
      <div className="grid-wrapper ag-theme-quartz audit-grid" style={{ height: "60vh" }}>
        <AgGridReact<AuditEvent>
          rowData={rows}
          columnDefs={auditColumns}
          defaultColDef={{ sortable: true, filter: true, resizable: true }}
          getRowId={(p) => p.data.event_id}
          rowClassRules={rowClassRules}
          onGridReady={onGridReady}
          suppressScrollOnNewData={true}
          animateRows={true}
          domLayout="normal"
        />
      </div>
    </div>
  );
}