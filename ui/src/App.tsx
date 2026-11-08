import React, { useState } from 'react';
import './App.css';
import { AuditPage } from './pages/AuditPage';
import { ProposalPage } from './pages/ProposalPage';
import { InvoicesPage } from './pages/InvoicesPage';
import { CustomerPage } from './pages/CustomerPage';
import {
  Activity,
  GitCompare,
  FileText,
  UserCheck,
  Shield,
  Layers,
} from 'lucide-react';

type TabType = 'audit' | 'comparator' | 'invoices' | 'customer';

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabType>('audit');
  const [selectedInvoiceId, setSelectedInvoiceId] = useState<string>('INV-001');
  const [customerToken, setCustomerToken] = useState<string>('demo-token-7f3a9c');

  const handleSelectInvoice = (id: string) => {
    setSelectedInvoiceId(id);
    setActiveTab('comparator');
  };

  const handleNavigateToCustomer = (token: string) => {
    setCustomerToken(token);
    setActiveTab('customer');
  };

  return (
    <div className="app-layout">
      {/* Top Navbar */}
      <header className="navbar">
        <div className="nav-brand">
          <div className="brand-icon">
            <Shield size={20} />
          </div>
          <div>
            <div className="brand-title">DueGuide Recovery</div>
            <div className="brand-subtitle">PayPal Sandbox & AG Grid Powered</div>
          </div>
        </div>

        <nav className="nav-tabs">
          <button
            className={`nav-tab ${activeTab === 'audit' ? 'active' : ''}`}
            onClick={() => setActiveTab('audit')}
          >
            <Activity size={16} /> Live Audit Grid
          </button>
          <button
            className={`nav-tab ${activeTab === 'comparator' ? 'active' : ''}`}
            onClick={() => setActiveTab('comparator')}
          >
            <GitCompare size={16} /> Comparator & Approval
          </button>
          <button
            className={`nav-tab ${activeTab === 'invoices' ? 'active' : ''}`}
            onClick={() => setActiveTab('invoices')}
          >
            <FileText size={16} /> Overdue Invoices
          </button>
          <button
            className={`nav-tab ${activeTab === 'customer' ? 'active' : ''}`}
            onClick={() => setActiveTab('customer')}
          >
            <UserCheck size={16} /> Customer Portal
          </button>
        </nav>

        <div className="nav-badges">
          <span className="badge-pill">
            <Layers size={12} /> Mock Data Active
          </span>
          <span className="badge-success">
            PayPal Sandbox
          </span>
        </div>
      </header>

      {/* Main Screen Content */}
      <main className="main-content">
        {activeTab === 'audit' && <AuditPage />}
        {activeTab === 'comparator' && (
          <ProposalPage
            invoiceId={selectedInvoiceId}
            onNavigateToCustomer={handleNavigateToCustomer}
          />
        )}
        {activeTab === 'invoices' && (
          <InvoicesPage onSelectInvoice={handleSelectInvoice} />
        )}
        {activeTab === 'customer' && (
          <CustomerPage
            token={customerToken}
            onBackToMerchant={() => setActiveTab('comparator')}
          />
        )}
      </main>

      {/* Mandatory permanent disclaimer (DoD requirement DEC-07 / Frontend.md) */}
      <footer className="app-footer">
        <div>
          <span className="disclaimer-text">
            Simulation subject to merchant approval and customer acceptance. Not financial or legal advice.
          </span>
        </div>
        <div>
          <span>DueGuide v1.0 • React + Vite + AG Grid Community</span>
        </div>
      </footer>
    </div>
  );
};

export default App;
