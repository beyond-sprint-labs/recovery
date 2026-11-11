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
  const [isPaused, setIsPaused] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [counts, setCounts] = useState({ total: 0, critical: 0 });
  
  const gridApiRef = useRef<GridApi<AuditEvent> | null>(null);
  const [gridReady, setGridReady] = useState(false);
  
  // Streaming references
  const cursorRef = useRef(0);
  const inFlightRef = useRef(false);

  const onGridReady = useCallback((e: GridReadyEvent<AuditEvent>) => {
    gridApiRef.current = e.api;
    setGridReady(true);
  }, []);

  useEffect(() => {
    if (!gridReady || isPaused) return;
    let alive = true;
    
    const tick = async () => {
      if (inFlightRef.current) return;
      inFlightRef.current = true;
      
      try {
        const page = await getAuditEvents(cursorRef.current);
        if (!alive) return;
        
        if (page.items.length > 0) {
          cursorRef.current = page.next_seq;
          const api = gridApiRef.current;
          
          // We filter out duplicates
          const fresh = page.items.filter((e) => !api?.getRowNode(e.event_id));
          
          if (fresh.length > 0) {
            // We insert without reloading the entire table.
            const added = api?.applyTransaction({ add: fresh, addIndex: 0 });
            
            if (added?.add && added.add.length > 0) {
              api?.flashCells({ rowNodes: added.add });
            }
            
            setCounts((c) => ({
              total: c.total + fresh.length,
              critical: c.critical + fresh.filter((e) => e.severity === "CRITICAL").length,
            }));
          }
        }
        setError(null);
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : String(e));
      } finally {
        inFlightRef.current = false;
      }
    };
    
    void tick();
    const id = window.setInterval(tick, POLL_MS);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, [gridReady, isPaused]);

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
        
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
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

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '20px', marginBottom: '32px' }}>
        <div className="card" style={{ padding: '24px' }}>
          <div className="muted" style={{ fontSize: '12px', textTransform: 'uppercase', letterSpacing: '0.5px', fontWeight: 600 }}>Total Events Streamed</div>
          <div style={{ fontSize: '36px', fontWeight: 800, marginTop: '8px', color: 'var(--text-primary)' }}>{counts.total}</div>
        </div>
        <div className="card" style={{ padding: '24px', borderLeft: '4px solid var(--status-danger)' }}>
          <div className="muted" style={{ fontSize: '12px', textTransform: 'uppercase', letterSpacing: '0.5px', fontWeight: 600, color: 'var(--status-danger)' }}>Critical Interceptions</div>
          <div style={{ fontSize: '36px', fontWeight: 800, marginTop: '8px', color: 'var(--status-danger)' }}>{counts.critical}</div>
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
      
      {/* NOTE: There is no longer a `rowData={rows}` here. Only `applyTransaction`. */}
      <div className="grid-wrapper ag-theme-quartz audit-grid" style={{ height: "60vh" }}>
        <AgGridReact<AuditEvent>
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