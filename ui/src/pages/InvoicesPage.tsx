import React, { useEffect, useState } from 'react';
import { AgGridReact } from 'ag-grid-react';
import { themeQuartz } from 'ag-grid-community';
import type { ColDef, ValueFormatterParams } from 'ag-grid-community';
import type { Invoice } from '../types/api';
import { apiClient } from '../api/client';

interface InvoicesPageProps {
  onSelectInvoice: (invoiceId: string) => void;
}

export const InvoicesPage: React.FC<InvoicesPageProps> = ({ onSelectInvoice }) => {
  const [invoices, setInvoices] = useState<Invoice[]>([]);

  useEffect(() => {
    async function loadData() {
      try {
        const data = await apiClient.getInvoices();
        setInvoices(data);
      } catch (err) {
        console.error('Failed to load invoices:', err);
      }
    }
    loadData();
  }, []);

  const columnDefs: ColDef<Invoice>[] = [
    {
      headerName: 'Invoice ID',
      field: 'id',
      width: 140,
      cellRenderer: (p: { value: string }) => (
        <span style={{ fontWeight: 600, fontFamily: 'monospace' }}>{p.value}</span>
      ),
    },
    {
      headerName: 'Customer',
      field: 'customer_name',
      flex: 1,
      minWidth: 200,
    },
    {
      headerName: 'Outstanding Balance',
      field: 'balance',
      width: 180,
      valueFormatter: (p: ValueFormatterParams) => `$${p.value} ${p.data?.currency || 'USD'}`,
      cellClassRules: {
        'text-danger font-semibold': (p) => p.data?.status === 'OVERDUE',
      },
    },
    {
      headerName: 'Due Date',
      field: 'due_date',
      width: 140,
    },
    {
      headerName: 'Status',
      field: 'status',
      width: 130,
      cellRenderer: (p: { value: string }) => {
        const isOverdue = p.value === 'OVERDUE';
        const isPaid = p.value === 'PAID';
        const cls = isOverdue ? 'badge-critical' : isPaid ? 'badge-success' : 'badge-info';
        return <span className={cls}>{p.value}</span>;
      },
    },
    {
      headerName: 'PayPal Invoice ID',
      field: 'paypal_invoice_id',
      width: 220,
      valueFormatter: (p: ValueFormatterParams) => p.value || 'Unlinked',
    },
    {
      headerName: 'Action',
      colId: 'action',
      width: 180,
      pinned: 'right',
      cellRenderer: (p: { data?: Invoice }) => {
        if (!p.data) return null;
        return (
          <button
            className="btn btn-primary btn-sm"
            onClick={() => onSelectInvoice(p.data!.id)}
            style={{ cursor: 'pointer', marginTop: '4px' }}
          >
            Review Options
          </button>
        );
      },
    },
  ];

  return (
    <div className="page-container">
      <div className="page-header">
        <div>
          <h2>Overdue Invoices</h2>
          <p className="subtitle">
            Merchant invoice portfolio: review overdue balances and dispatch mathematically valid repayment proposals.
          </p>
        </div>
        <div className="header-actions">
          <button className="btn btn-secondary" onClick={() => onSelectInvoice('INV-001')}>
            Open INV-001 Comparator
          </button>
        </div>
      </div>

      <div className="grid-wrapper">
        <AgGridReact<Invoice>
          theme={themeQuartz}
          rowData={invoices}
          columnDefs={columnDefs}
          pagination={true}
          paginationPageSize={10}
          paginationPageSizeSelector={[10, 20, 50]}
          defaultColDef={{
            sortable: true,
            filter: true,
            resizable: true,
          }}
        />
      </div>
    </div>
  );
};
