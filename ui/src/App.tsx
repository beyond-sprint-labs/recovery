import React, { useState, Suspense, lazy } from 'react';
import './App.css';

// Lazy loaded page components for optimal code-splitting and scalability
const AuditPage = lazy(() => import('./pages/AuditPage').then((m) => ({ default: m.AuditPage })));
const ProposalPage = lazy(() => import('./pages/ProposalPage').then((m) => ({ default: m.ProposalPage })));
const InvoicesPage = lazy(() => import('./pages/InvoicesPage').then((m) => ({ default: m.InvoicesPage })));
const CustomerPage = lazy(() => import('./pages/CustomerPage').then((m) => ({ default: m.CustomerPage })));

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
      <header className="navbar" role="banner">
        <div className="nav-brand">
          <div>
            <div className="brand-title">DueGuide Recovery</div>
            <div className="brand-subtitle">Financial Policy & Settlement Engine</div>
          </div>
        </div>

        <nav className="nav-tabs" role="tablist" aria-label="Main Navigation">
          <button
            role="tab"
            aria-selected={activeTab === 'audit'}
            className={`nav-tab ${activeTab === 'audit' ? 'active' : ''}`}
            onClick={() => setActiveTab('audit')}
          >
            Live Audit Grid
          </button>
          <button
            role="tab"
            aria-selected={activeTab === 'comparator'}
            className={`nav-tab ${activeTab === 'comparator' ? 'active' : ''}`}
            onClick={() => setActiveTab('comparator')}
          >
            Comparator & Approval
          </button>
          <button
            role="tab"
            aria-selected={activeTab === 'invoices'}
            className={`nav-tab ${activeTab === 'invoices' ? 'active' : ''}`}
            onClick={() => setActiveTab('invoices')}
          >
            Overdue Invoices
          </button>
          <button
            role="tab"
            aria-selected={activeTab === 'customer'}
            className={`nav-tab ${activeTab === 'customer' ? 'active' : ''}`}
            onClick={() => setActiveTab('customer')}
          >
            Customer Portal
          </button>
        </nav>

        <div className="nav-status-group">
          <span className="badge-status badge-info">
            Offline Mocks
          </span>
          <span className="badge-status badge-success">
            PayPal Sandbox
          </span>
        </div>
      </header>

      {/* Main Screen Content with Suspense for lazy route chunks */}
      <main className="main-content" role="main">
        <Suspense
          fallback={
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '360px', color: '#64748b' }}>
              <span>Loading view...</span>
            </div>
          }
        >
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
        </Suspense>
      </main>

      {/* Mandatory permanent disclaimer (DEC-07 / Frontend.md) */}
      <footer className="app-footer" role="contentinfo">
        <div>
          <span className="disclaimer-text">
            Simulation subject to merchant approval and customer acceptance. Not financial or legal advice.
          </span>
        </div>
        <div>
          <span>DueGuide v1.0 • React + AG Grid Community</span>
        </div>
      </footer>
    </div>
  );
};

export default App;
