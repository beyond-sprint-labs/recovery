import React, { useState, useEffect } from 'react';
import { apiClient } from '../api/client';
import type { CustomerProposalView, CustomerRespondResponse } from '../types/api';
import {
  CheckCircle,
  XCircle,
  RefreshCw,
} from 'lucide-react';

interface CustomerPageProps {
  token?: string;
  onBackToMerchant?: () => void;
}

export const CustomerPage: React.FC<CustomerPageProps> = ({
  token = 'demo-token-7f3a9c',
  onBackToMerchant,
}) => {
  const [proposalView, setProposalView] = useState<CustomerProposalView | null>(null);
  const [loading, setLoading] = useState(true);
  const [executing, setExecuting] = useState(false);
  const [stepIndex, setStepIndex] = useState(0);
  const [result, setResult] = useState<CustomerRespondResponse | null>(null);

  useEffect(() => {
    async function loadProposal() {
      try {
        setLoading(true);
        const data = await apiClient.getCustomerProposal(token);
        setProposalView(data);
      } catch (err) {
        console.error('Failed to load customer proposal:', err);
      } finally {
        setLoading(false);
      }
    }
    loadProposal();
  }, [token]);

  const handleDecision = async (decision: 'ACCEPT' | 'DECLINE') => {
    setExecuting(true);
    setStepIndex(0);

    if (decision === 'ACCEPT') {
      const timer1 = setTimeout(() => setStepIndex(1), 600);
      const timer2 = setTimeout(() => setStepIndex(2), 1200);
      const timer3 = setTimeout(() => setStepIndex(3), 1800);

      try {
        const res = await apiClient.respondAsCustomer(token, { decision });
        setResult(res);
      } catch (err) {
        console.error('Error in decision response:', err);
      } finally {
        clearTimeout(timer1);
        clearTimeout(timer2);
        clearTimeout(timer3);
        setExecuting(false);
      }
    } else {
      try {
        const res = await apiClient.respondAsCustomer(token, { decision });
        setResult(res);
      } catch (err) {
        console.error('Decline error:', err);
      } finally {
        setExecuting(false);
      }
    }
  };

  if (loading) {
    return (
      <div className="customer-wrapper">
        <div className="customer-card text-center" style={{ padding: '40px' }}>
          <RefreshCw className="icon-spin text-primary" size={28} style={{ margin: '0 auto 12px' }} />
          <p className="text-secondary text-sm">Loading approved proposal details...</p>
        </div>
      </div>
    );
  }

  if (result) {
    const isAccepted = result.status === 'EXECUTED';
    return (
      <div className="customer-wrapper">
        <div className="customer-card">
          <div className="text-center" style={{ marginBottom: '24px' }}>
            {isAccepted ? (
              <CheckCircle size={44} className="text-success" style={{ margin: '0 auto 12px' }} />
            ) : (
              <XCircle size={44} className="text-danger" style={{ margin: '0 auto 12px' }} />
            )}
            <h2 style={{ margin: '0 0 6px 0' }}>{isAccepted ? 'Repayment Plan Activated' : 'Proposal Declined'}</h2>
            <p className="subtitle">
              {isAccepted
                ? 'Your agreement has been recorded. Replacement invoice schedule is active on PayPal Sandbox.'
                : 'You have declined this repayment offer. The merchant has been notified.'}
            </p>
          </div>

          {isAccepted && result.paypal && (
            <div className="paypal-receipt">
              <h4 style={{ margin: '0 0 10px 0', fontSize: '13px' }}>PayPal Sandbox Details:</h4>
              <div className="receipt-row">
                <span>Original Invoice:</span>
                <span className="font-mono">{result.paypal.original_invoice_id} (Cancelled)</span>
              </div>
              <div className="receipt-row">
                <span>Replacement Invoice:</span>
                <span className="font-mono highlight-green">{result.paypal.new_invoice_id} (Active)</span>
              </div>
              <div className="receipt-row">
                <span>Initial Due Today:</span>
                <span className="font-mono font-bold">${proposalView?.alternative.amount_due_now} USD</span>
              </div>
              <div className="receipt-row">
                <span>Payment Confirmation:</span>
                <span className="badge-success">CONFIRMED (Sandbox Demo)</span>
              </div>
            </div>
          )}

          {onBackToMerchant && (
            <button className="btn btn-secondary btn-block" style={{ marginTop: '20px' }} onClick={onBackToMerchant}>
              Return to Merchant Dashboard
            </button>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="customer-wrapper">
      <div className="customer-card">
        <div className="customer-header">
          <span className="brand-text">DueGuide Customer Portal</span>
          <span className="badge-status badge-info">Merchant Pre-Approved</span>
        </div>

        <h3 style={{ margin: '0 0 10px 0', fontSize: '18px' }}>Repayment Proposal</h3>
        <p className="customer-message-box">
          {proposalView?.customer_message}
        </p>

        <div className="customer-terms-summary">
          <div className="term-box">
            <span className="term-label">Outstanding Balance</span>
            <span className="term-value font-mono font-bold">${proposalView?.original_balance} USD</span>
          </div>
          <div className="term-box highlight-box">
            <span className="term-label">Pay Today</span>
            <span className="term-value font-mono font-bold highlight-green">${proposalView?.alternative.amount_due_now} USD</span>
          </div>
          <div className="term-box">
            <span className="term-label">Total Payment</span>
            <span className="term-value font-mono font-bold">${proposalView?.alternative.total_paid} USD</span>
          </div>
        </div>

        {proposalView?.alternative.schedule && proposalView.alternative.schedule.length > 0 && (
          <div style={{ marginTop: '16px' }}>
            <h4 style={{ margin: '0 0 8px 0', fontSize: '12px' }}>Payment Schedule:</h4>
            <table className="schedule-table">
              <thead>
                <tr>
                  <th>Installment</th>
                  <th>Due Date</th>
                  <th>Amount</th>
                </tr>
              </thead>
              <tbody>
                {proposalView.alternative.schedule.map((s) => (
                  <tr key={s.n}>
                    <td>{s.n === 0 ? 'Down Payment (Today)' : `Installment #${s.n}`}</td>
                    <td>{s.due_date}</td>
                    <td className="font-mono font-semibold">${s.amount} USD</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {executing ? (
          <div className="execution-stepper">
            <div className="text-center" style={{ marginBottom: '14px' }}>
              <RefreshCw className="icon-spin text-primary" size={24} style={{ margin: '0 auto 8px' }} />
              <h4 style={{ margin: '0 0 4px 0', fontSize: '14px' }}>Processing PayPal Transaction...</h4>
              <p className="text-sm text-secondary" style={{ margin: 0 }}>Orchestrating replacement invoice on PayPal Sandbox</p>
            </div>

            <div className="step-item">
              <span className={`step-circle ${stepIndex >= 1 ? 'step-done' : 'step-active'}`}>1</span>
              <span>Create replacement draft invoice</span>
            </div>
            <div className="step-item">
              <span className={`step-circle ${stepIndex >= 2 ? 'step-done' : stepIndex === 1 ? 'step-active' : ''}`}>2</span>
              <span>Cancel original overdue invoice</span>
            </div>
            <div className="step-item">
              <span className={`step-circle ${stepIndex >= 3 ? 'step-done' : stepIndex === 2 ? 'step-active' : ''}`}>3</span>
              <span>Dispatch replacement PayPal invoice</span>
            </div>
          </div>
        ) : (
          <div className="binary-actions">
            <button
              className="btn btn-success btn-lg"
              style={{ flex: 1 }}
              onClick={() => handleDecision('ACCEPT')}
            >
              Accept Repayment Plan
            </button>
            <button
              className="btn btn-outline-danger btn-lg"
              style={{ flex: 1 }}
              onClick={() => handleDecision('DECLINE')}
            >
              Decline Offer
            </button>
          </div>
        )}

        <div className="customer-disclaimer">
          {proposalView?.simulation_notice ||
            'Simulation subject to merchant approval and customer acceptance. Not financial or legal advice.'}
        </div>
      </div>
    </div>
  );
};
