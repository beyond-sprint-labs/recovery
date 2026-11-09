import type { ColDef, ValueFormatterParams } from 'ag-grid-community';
import type { AuditEvent } from '../types/api';

/**
 * Value formatter for money amounts without using float arithmetic (DEC-02)
 */
export const formatMoneyString = (params: ValueFormatterParams): string => {
  if (params.value === null || params.value === undefined) return '-';
  const val = String(params.value);
  return `$${val}`;
};

/**
 * Date/time formatter for ISO timestamps
 */
export const formatTimestamp = (params: ValueFormatterParams): string => {
  if (!params.value) return '-';
  try {
    const d = new Date(params.value);
    return d.toLocaleTimeString([], { hour12: false }) + ` (${d.toISOString().slice(0, 10)})`;
  } catch {
    return String(params.value);
  }
};

export const auditColDefs: ColDef<AuditEvent>[] = [
  {
    headerName: 'Seq',
    field: 'seq',
    width: 90,
    pinned: 'left',
    sort: 'desc',
    filter: 'agNumberColumnFilter',
    cellRenderer: (params: { value: number }) => (
      <span className="font-mono font-bold text-gray-700">{params.value}</span>
    ),
  },
  {
    headerName: 'Timestamp',
    field: 'ts',
    width: 170,
    pinned: 'left',
    valueFormatter: formatTimestamp,
    filter: 'agDateColumnFilter',
  },
  {
    headerName: 'Severity',
    field: 'severity',
    width: 120,
    cellRenderer: (params: { value: string }) => {
      const isCritical = params.value === 'CRITICAL';
      const isWarning = params.value === 'WARNING';
      const cls = isCritical ? 'badge-critical' : isWarning ? 'badge-warning' : 'badge-info';
      return <span className={cls}>{params.value || '-'}</span>;
    },
    filter: 'agTextColumnFilter',
  },
  {
    headerName: 'Action',
    field: 'action',
    width: 230,
    filter: 'agTextColumnFilter',
    cellRenderer: (params: { value: string }) => {
      const isBlocked = params.value === 'PROPOSAL_BLOCKED';
      const isPaypal = params.value && params.value.startsWith('PAYPAL_');
      const isPaid = params.value === 'PAYMENT_CONFIRMED';
      return (
        <span
          style={{
            fontWeight: 700,
            color: isBlocked ? '#dc2626' : isPaid ? '#16a34a' : isPaypal ? '#2563eb' : '#0f172a',
          }}
        >
          {params.value || '-'}
        </span>
      );
    },
  },
  {
    headerName: 'State Transition',
    width: 200,
    valueGetter: (params) => {
      const from = params.data?.state_from || 'INIT';
      const to = params.data?.state_to || '-';
      return `${from} → ${to}`;
    },
    cellRenderer: (params: { value: string }) => (
      <span className="font-mono text-xs font-semibold text-gray-600">{params.value}</span>
    ),
    filter: 'agTextColumnFilter',
  },
  {
    headerName: 'Invoice',
    field: 'invoice_id',
    width: 120,
    cellRenderer: (params: { value: string }) => (
      <span className="font-mono font-bold text-gray-800">{params.value || '-'}</span>
    ),
    filter: 'agTextColumnFilter',
  },
  {
    headerName: 'Proposal',
    field: 'proposal_id',
    width: 140,
    cellRenderer: (params: { value?: string | null }) => (
      <span className="font-mono text-gray-600">{params.value || '-'}</span>
    ),
    filter: 'agTextColumnFilter',
  },
  {
    headerName: 'Actor',
    width: 220,
    valueGetter: (params) => {
      const a = params.data?.actor;
      return a ? `${a.type}:${a.id}` : '-';
    },
    cellRenderer: (params: { value: string }) => (
      <span className="font-mono text-xs text-gray-700" title={params.value}>{params.value}</span>
    ),
    filter: 'agTextColumnFilter',
  },
  {
    headerName: 'PayPal Called?',
    field: 'paypal_called',
    width: 150,
    cellRenderer: (params: { value: boolean }) => {
      return params.value ? (
        <span style={{ color: '#059669', fontWeight: 700 }}>YES (Called)</span>
      ) : (
        <span style={{ color: '#6b7280', fontWeight: 600 }}>NO</span>
      );
    },
    filter: true,
  },
  {
    headerName: 'Policy Rule',
    width: 180,
    valueGetter: (params) => {
      const r = params.data?.rule;
      if (!r) return '-';
      return `${r.code} (${r.attempted}${r.unit ? r.unit : ''} > ${r.limit}${r.unit ? r.unit : ''})`;
    },
    cellRenderer: (params: { value: string }) => {
      if (params.value === '-') return <span className="text-gray-400">-</span>;
      return <span className="badge-critical font-mono">{params.value}</span>;
    },
    filter: 'agTextColumnFilter',
  },
  {
    headerName: 'PayPal Ref',
    field: 'paypal_ref',
    width: 190,
    cellRenderer: (params: { value?: string | null }) => (
      <span className="font-mono text-xs text-gray-700">{params.value || '-'}</span>
    ),
    filter: 'agTextColumnFilter',
  },
  {
    headerName: 'Summary',
    field: 'summary',
    flex: 1,
    minWidth: 320,
    filter: 'agTextColumnFilter',
  },
];
