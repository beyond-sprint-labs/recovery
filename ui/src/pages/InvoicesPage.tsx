import React, { useEffect, useState } from 'react';
import { AgGridReact } from 'ag-grid-react';
import { themeQuartz } from 'ag-grid-community';
import type { ColDef, ValueFormatterParams } from 'ag-grid-community';
import type { Invoice } from '../types/api';
import { apiClient } from '../api/client';
import { FileText, ArrowRight } from 'lucide-react';

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
      cellRenderer: (p: { value: string }) => `<span style="font-weight: 600; font-family: monospace;">${p.value}</span>`,
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
        const color = isOverdue ? '#dc2626' : isPaid ? '#16a34a' : '#6b7280';
        const bg = isOverdue ? '#fee2e2' : isPaid ? '#dcfce7' : '#f3f4f6';
        return `<span style="background: ${bg}; color: ${color}; padding: 3px 8px; border-radius: 9999px; font-size: 11px; font-weight: 700;">${p.value}</span>`;
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
      width: 180,
      cellRenderer: (p: { data: Invoice }) => {
        return `<button class="btn btn-primary btn-sm" id="btn-select-${p.data.id}">
          Resolve Alternative &rarr;
        </button>`;
      },
      onCellClicked: (p) => {
        if (p.data) {
          onSelectInvoice(p.data.id);
        }
      },
    },
  ];

  return (
    <div className="page-container">
      <div className="page-header">
        <div>
          <div className="badge-pill">
            <FileText size={14} /> Merchant Portfolio
          </div>
          <h2>Overdue Invoices</h2>
          <p className="subtitle">
            Manage overdue accounts, review active PayPal invoices, and draft AI-assisted settlement alternatives.
          </p>
        </div>
        <div className="header-actions">
          <button className="btn btn-secondary" onClick={() => onSelectInvoice('INV-001')}>
            Open INV-001 Comparator <ArrowRight size={16} />
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
