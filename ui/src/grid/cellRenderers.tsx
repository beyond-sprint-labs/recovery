import type { ICellRendererParams } from "ag-grid-community";
import type { AuditEvent } from "../types/api";

export function SeverityPill(params: ICellRendererParams<AuditEvent, AuditEvent["severity"]>) {
  const severity = params.value;
  if (!severity) return null;

  const palette = {
    CRITICAL: { bg: '#fef2f2', color: '#991b1b', dot: '#ef4444', border: '#fecaca' },
    WARN: { bg: '#fffbeb', color: '#92400e', dot: '#f59e0b', border: '#fde68a' },
    INFO: { bg: '#f0f9ff', color: '#075985', dot: '#0ea5e9', border: '#bae6fd' },
  };
  const config = palette[severity] ?? palette.INFO;

  return (
    <div style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: '6px', background: config.bg, color: config.color, padding: '6px 12px', borderRadius: '100px', fontSize: '11px', fontWeight: 700, letterSpacing: '0.5px', height: '24px', whiteSpace: 'nowrap', border: `1px solid ${config.border}` }}>
      <div style={{ width: '6px', height: '6px', borderRadius: '50%', background: config.dot, flexShrink: 0 }} />
      {severity}
    </div>
  );
}

export function ActionBadge(params: ICellRendererParams<AuditEvent, string>) {
  const action = params.value;
  if (!action) return null;
  
  return (
    <span style={{ 
      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
      fontSize: '13px',
      fontWeight: 600,
      color: 'var(--text-primary)',
      letterSpacing: '-0.2px'
    }}>
      {action}
    </span>
  );
}

export function PaypalCalled(params: ICellRendererParams<AuditEvent, boolean>) {
  const called = params.value;
  if (called === undefined || called === null) return null;

  return called ? (
    <span style={{ color: 'var(--status-success)', fontWeight: 600, fontSize: '13px' }}>✔ Yes</span>
  ) : (
    <span style={{ color: 'var(--text-tertiary)', fontSize: '13px' }}>— No</span>
  );
}