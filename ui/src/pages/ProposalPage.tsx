import React, { useState, useEffect } from 'react';
import { apiClient } from '../api/client';
import type { Proposal, Alternative, ApproveResponse } from '../types/api';
import {
  ShieldAlert,
  CheckCircle2,
  ExternalLink,
  RefreshCw,
} from 'lucide-react';

interface ProposalPageProps {
  invoiceId: string;
  onNavigateToCustomer: (token: string) => void;
}

export const ProposalPage: React.FC<ProposalPageProps> = ({
  invoiceId = 'INV-001',
  onNavigateToCustomer,
}) => {
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [scenario, setScenario] = useState<'STANDARD' | 'BLOCKED'>('STANDARD');
  const [loading, setLoading] = useState(false);
  const [approvedResult, setApprovedResult] = useState<ApproveResponse | null>(null);
  const [approvingType, setApprovingType] = useState<string | null>(null);
  const [reconciling, setReconciling] = useState(false);

  const fetchProposal = async (mode: 'STANDARD' | 'BLOCKED') => {
    setLoading(true);
    setApprovedResult(null);
    try {
      const data = await apiClient.createProposal(invoiceId, mode);
      setProposal(data);
    } catch (err) {
      console.error('Failed to create proposal:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchProposal(scenario);
  }, [scenario, invoiceId]);

  const handleApproveOption = async (alt: Alternative) => {
    if (!proposal) return;
    setApprovingType(alt.type);
    try {
      const res = await apiClient.approve(proposal.proposal_id, {
        alternative_type: alt.type,
        note: `Approved alternative: ${alt.type}`,
      });
      setApprovedResult(res);
      setProposal((prev) => (prev ? { ...prev, status: 'PENDING_CUSTOMER' } : null));
    } catch (err) {
      console.error('Approve failed:', err);
    } finally {
      setApprovingType(null);
    }
  };

  const handleReconcile = async () => {
    setReconciling(true);
    try {
      await apiClient.reconcile(invoiceId);
      alert('Reconciliation with PayPal Sandbox completed successfully.');
    } catch (err) {
      console.error('Reconciliation error:', err);
    } finally {
      setReconciling(false);
    }
  };

  const isBlocked = proposal?.status === 'BLOCKED';

  return (
    <div className="page-container">
      <div className="page-header">
        <div>
          <h2>Repayment Proposal Comparator</h2>
          <p className="subtitle">
            Human-in-the-loop merchant approval: select and pre-approve a mathematically valid settlement alternative.
          </p>
        </div>

        <div className="header-actions">
          <label htmlFor="scenario-select" className="text-sm font-semibold">
            Scenario:
          </label>
          <select
            id="scenario-select"
            className="select-input"
            value={scenario}
            onChange={(e) => setScenario(e.target.value as 'STANDARD' | 'BLOCKED')}
          >
            <option value="STANDARD">Standard (2 Policy-Compliant Options)</option>
            <option value="BLOCKED">S03 Policy Violation (40% Discount - BLOCKED)</option>
          </select>

          <button
            className="btn btn-secondary"
            onClick={() => fetchProposal(scenario)}
            disabled={loading}
            aria-label="Refresh proposal calculation"
          >
            <RefreshCw size={14} className={loading ? 'icon-spin' : ''} /> Refresh
          </button>
        </div>
      </div>

      {loading ? (
        <div className="card text-center" style={{ padding: '40px' }}>
          <RefreshCw className="icon-spin text-primary" size={24} style={{ margin: '0 auto 12px' }} />
          <p className="text-secondary text-sm">Evaluating policy rules and amortization formulas...</p>
        </div>
      ) : isBlocked ? (
        <div className="card card-blocked">
          <div className="card-blocked-header">
            <ShieldAlert size={26} className="text-danger" />
            <div>
              <h3 className="text-danger" style={{ margin: '0 0 4px 0' }}>PROPOSAL BLOCKED BY FINANCIAL GUARDRAIL</h3>
              <p className="text-sm text-secondary" style={{ margin: 0 }}>
                The proposed repayment alternative exceeded defined merchant risk thresholds.
              </p>
            </div>
          </div>

          <div className="blocked-details">
            <div className="detail-item">
              <span className="detail-label">Interception Rule:</span>
              <span className="badge-critical font-mono">MAX_DISCOUNT_PCT</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Merchant Limit:</span>
              <span className="font-semibold">15%</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Attempted Discount:</span>
              <span className="font-semibold text-danger">40%</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">PayPal Protection:</span>
              <span className="badge-success">NOT CALLED (Zero External Risk)</span>
            </div>
          </div>

          <p className="blocked-summary">
            <strong>Engine Verdict:</strong> Proposed 40% settlement discount exceeds merchant limit of 15%; PayPal not called.
          </p>

          <div style={{ marginTop: '14px' }}>
            <span className="text-sm text-secondary">
              Logged to the <strong>Live Audit Trail</strong> with severity <span className="badge-critical font-mono">CRITICAL</span>.
            </span>
          </div>
        </div>
      ) : (
        <>
          {approvedResult && (
            <div className="alert-banner alert-success">
              <CheckCircle2 size={18} />
              <div style={{ flex: 1 }}>
                <strong>Proposal Approved & Ready for Customer</strong>
                <p className="text-sm" style={{ margin: 0 }}>
                  Pre-approved alternative locked. The single offer is available for binary customer response.
                </p>
              </div>
              <button
                className="btn btn-primary btn-sm"
                onClick={() => onNavigateToCustomer('demo-token-7f3a9c')}
              >
                Open Customer Portal <ExternalLink size={14} />
              </button>
            </div>
          )}

          <div className="proposal-overview">
            <div className="overview-item">
              <span className="label">Invoice Ref:</span>
              <span className="val font-mono font-bold">{proposal?.invoice_id || invoiceId}</span>
            </div>
            <div className="overview-item">
              <span className="label">Status:</span>
              <span className="badge-status badge-info">
                {proposal?.status}
              </span>
            </div>
            <div className="overview-item">
              <span className="label">Original Outstanding:</span>
              <span className="val font-semibold font-mono">$1000.00 USD</span>
            </div>
            <div className="overview-item">
              <span className="label">Policy Verification:</span>
              <span className="val text-success font-semibold">
                PASS (Within Limits)
              </span>
            </div>
          </div>

          <div className="comparator-grid">
            {proposal?.alternatives.map((alt, idx) => {
              const isSettlement = alt.type === 'settlement_discount';
              const title = isSettlement
                ? 'Option 1: Immediate Settlement Discount'
                : 'Option 2: Down Payment + Structured Installments';

              return (
                <div key={alt.type} className="comparator-card">
                  <div className="card-header">
                    <div>
                      <span className="option-tag">Alternative {idx + 1}</span>
                      <h3 style={{ margin: '8px 0 0 0', fontSize: '16px' }}>{title}</h3>
                    </div>
                  </div>

                  <div className="financial-breakdown">
                    <div className="metric-row">
                      <span className="metric-name">Due Immediately:</span>
                      <span className="metric-value font-mono highlight-green">
                        ${alt.amount_due_now} USD
                      </span>
                    </div>

                    {!isSettlement && (
                      <div className="metric-row">
                        <span className="metric-name">Installments:</span>
                        <span className="metric-value font-mono">
                          {alt.terms.installments} monthly x ${alt.installment_amount}
                        </span>
                      </div>
                    )}

                    <div className="metric-row">
                      <span className="metric-name">Total Recovered:</span>
                      <span className="metric-value font-mono font-bold">
                        ${alt.total_paid} USD
                      </span>
                    </div>

                    <div className="metric-row">
                      <span className="metric-name">Difference vs Balance:</span>
                      <span className={`metric-value font-mono ${Number(alt.merchant_difference_vs_balance || 0) < 0 ? 'text-danger' : 'text-success'}`}>
                        ${alt.merchant_difference_vs_balance || '0.00'} USD
                      </span>
                    </div>

                    <div className="metric-row">
                      <span className="metric-name">Policy Status:</span>
                      <span className="badge-success">PASSED</span>
                    </div>
                  </div>

                  <div className="schedule-preview">
                    <h4 style={{ margin: '0 0 8px 0', fontSize: '12px' }}>Repayment Schedule (DEC-02 Decimal Strings):</h4>
                    <table className="schedule-table">
                      <thead>
                        <tr>
                          <th>#</th>
                          <th>Due Date</th>
                          <th>Amount</th>
                          <th>Principal</th>
                          <th>Interest</th>
                        </tr>
                      </thead>
                      <tbody>
                        {alt.schedule.map((row) => (
                          <tr key={row.n}>
                            <td>{row.n}</td>
                            <td>{row.due_date}</td>
                            <td className="font-mono">${row.amount}</td>
                            <td className="font-mono">${row.principal}</td>
                            <td className="font-mono">${row.interest}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  <div className="card-footer" style={{ marginTop: 'auto' }}>
                    <button
                      className="btn btn-primary btn-block"
                      disabled={proposal.status !== 'PENDING_MERCHANT' || approvingType !== null}
                      onClick={() => handleApproveOption(alt)}
                    >
                      {approvingType === alt.type ? (
                        <>
                          <RefreshCw size={14} className="icon-spin" /> Submitting Approval...
                        </>
                      ) : (
                        'Approve This Alternative'
                      )}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>

          <div className="card" style={{ marginTop: '20px' }}>
            <h4 style={{ margin: '0 0 6px 0', fontSize: '13px' }}>Customer Communication Text:</h4>
            <p className="message-box">
              {proposal?.customer_message ||
                'Your invoice INV-001 has an outstanding balance of $1000.00. You can settle it by paying $300.00 now plus 3 monthly installments of $240.37, for a total of $1021.10.'}
            </p>
          </div>

          {/* Plan B Quick Action */}
          <div className="plan-b-section">
            <span className="text-sm text-secondary">
              Demo Short-Circuit:
            </span>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => onNavigateToCustomer('demo-token-7f3a9c')}
              >
                Open Customer Decision View
              </button>
              <button
                className="btn btn-secondary btn-sm"
                onClick={handleReconcile}
                disabled={reconciling}
              >
                <RefreshCw size={13} className={reconciling ? 'icon-spin' : ''} /> Reconcile with PayPal
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
};
