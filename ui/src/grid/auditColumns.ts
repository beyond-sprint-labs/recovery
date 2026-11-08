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
    cellClassRules: {
      'badge-critical': (params) => params.value === 'CRITICAL',
      'badge-warning': (params) => params.value === 'WARNING',
      'badge-info': (params) => params.value === 'INFO',
    },
    filter: 'agTextColumnFilter',
  },
  {
    headerName: 'Action',
    field: 'action',
    width: 220,
    filter: 'agTextColumnFilter',
    cellRenderer: (params: { value: string }) => {
      const isBlocked = params.value === 'PROPOSAL_BLOCKED';
      return `<span style="font-weight: 600; ${isBlocked ? 'color: #dc2626;' : ''}">${params.value || '-'}</span>`;
    },
  },
  {
    headerName: 'State Transition',
    width: 190,
    valueGetter: (params) => {
      const from = params.data?.state_from || 'INIT';
      const to = params.data?.state_to || '-';
      return `${from} → ${to}`;
    },
    filter: 'agTextColumnFilter',
  },
  {
    headerName: 'Invoice',
    field: 'invoice_id',
    width: 120,
    filter: 'agTextColumnFilter',
  },
  {
    headerName: 'Proposal',
    field: 'proposal_id',
    width: 140,
    valueFormatter: (p) => p.value || '-',
    filter: 'agTextColumnFilter',
  },
  {
    headerName: 'Actor',
    width: 160,
    valueGetter: (params) => {
      const a = params.data?.actor;
      return a ? `${a.type}:${a.id}` : '-';
    },
    filter: 'agTextColumnFilter',
  },
  {
    headerName: 'PayPal Called?',
    field: 'paypal_called',
    width: 140,
    cellRenderer: (params: { value: boolean }) => {
      return params.value
        ? `<span style="color: #059669; font-weight: 600;">YES (Called)</span>`
        : `<span style="color: #6b7280;">NO</span>`;
    },
    filter: true,
  },
  {
    headerName: 'Policy Rule',
    width: 170,
    valueGetter: (params) => {
      const r = params.data?.rule;
      if (!r) return '-';
      return `${r.code} (${r.attempted}${r.unit ? r.unit : ''} > ${r.limit}${r.unit ? r.unit : ''})`;
    },
    filter: 'agTextColumnFilter',
  },
  {
    headerName: 'PayPal Ref',
    field: 'paypal_ref',
    width: 180,
    valueFormatter: (p) => p.value || '-',
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
