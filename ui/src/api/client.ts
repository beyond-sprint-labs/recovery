import type {
  Invoice,
  Proposal,
  ApproveRequest,
  ApproveResponse,
  CustomerProposalView,
  CustomerRespondRequest,
  CustomerRespondResponse,
  AuditEvent,
} from '../types/api';

import mockInvoices from '../mocks/invoices.json';
import mockProposalPending from '../mocks/proposal_pending.json';
import mockProposalBlocked from '../mocks/proposal_blocked.json';
import mockApproveResponse from '../mocks/approve_response.json';
import mockCustomerProposal from '../mocks/customer_proposal.json';
import mockAuditSeed from '../mocks/audit_events.seed.json';
import mockAuditStream from '../mocks/audit_events.stream.json';

const USE_MOCKS = import.meta.env.VITE_USE_MOCKS !== 'false';
const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';

// Internal state for mock streaming
let streamedIndex = 0;
const currentAuditEvents: AuditEvent[] = [...(mockAuditSeed as AuditEvent[])];

function delay(min = 300, max = 600): Promise<void> {
  const ms = Math.floor(Math.random() * (max - min + 1)) + min;
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export const apiClient = {
  isMockMode(): boolean {
    return USE_MOCKS;
  },

  async getInvoices(): Promise<Invoice[]> {
    if (USE_MOCKS) {
      await delay();
      return mockInvoices as Invoice[];
    }
    const res = await fetch(`${BASE_URL}/invoices`);
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    return res.json();
  },

  async createProposal(invoiceId: string, scenario: 'STANDARD' | 'BLOCKED' = 'STANDARD'): Promise<Proposal> {
    if (USE_MOCKS) {
      await delay();
      if (scenario === 'BLOCKED') {
        return mockProposalBlocked as unknown as Proposal;
      }
      return mockProposalPending as unknown as Proposal;
    }
    const res = await fetch(`${BASE_URL}/proposals`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ invoice_id: invoiceId }),
    });
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    return res.json();
  },

  async approve(proposalId: string, req: ApproveRequest): Promise<ApproveResponse> {
    if (USE_MOCKS) {
      await delay();
      const res = { ...mockApproveResponse } as unknown as ApproveResponse;
      res.proposal_id = proposalId;
      return res;
    }
    const res = await fetch(`${BASE_URL}/proposals/${proposalId}/approve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    return res.json();
  },

  async getCustomerProposal(token: string): Promise<CustomerProposalView> {
    if (USE_MOCKS) {
      await delay();
      return mockCustomerProposal as unknown as CustomerProposalView;
    }
    const res = await fetch(`${BASE_URL}/customer/proposals/${token}`);
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    return res.json();
  },

  async respondAsCustomer(token: string, req: CustomerRespondRequest): Promise<CustomerRespondResponse> {
    if (USE_MOCKS) {
      await delay(1200, 2000); // Simulate PayPal synchronous orchestration
      if (req.decision === 'DECLINE') {
        return {
          proposal_id: 'prop_7f3a9c',
          status: 'DECLINED',
        };
      }
      return {
        proposal_id: 'prop_7f3a9c',
        status: 'EXECUTED',
        paypal: {
          new_invoice_id: 'INV2-K4M9-2P7X-8Q3N-V5RD',
          original_invoice_id: 'INV2-6W2K-7D9Q-4M3P-R8TX',
          steps: [
            { step: 'DRAFT_CREATED', status: 'OK', paypal_id: 'INV2-K4M9-2P7X-8Q3N-V5RD' },
            { step: 'ORIGINAL_CANCELLED', status: 'OK', paypal_id: 'INV2-6W2K-7D9Q-4M3P-R8TX' },
            { step: 'INVOICE_SENT', status: 'OK', paypal_id: 'INV2-K4M9-2P7X-8Q3N-V5RD' },
          ],
        },
      };
    }
    const res = await fetch(`${BASE_URL}/customer/proposals/${token}/respond`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    return res.json();
  },

  async reconcile(invoiceId: string): Promise<{ invoice_id: string; status: string }> {
    if (USE_MOCKS) {
      await delay();
      return { invoice_id: invoiceId, status: 'RECONCILED' };
    }
    const res = await fetch(`${BASE_URL}/reconcile/${invoiceId}`, { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    return res.json();
  },

  async getAuditEvents(afterSeq = 0): Promise<AuditEvent[]> {
    if (USE_MOCKS) {
      await delay(100, 250);
      if (streamedIndex < (mockAuditStream as AuditEvent[]).length) {
        const nextEvent = (mockAuditStream as AuditEvent[])[streamedIndex++];
        if (!currentAuditEvents.some((e) => e.event_id === nextEvent.event_id)) {
          currentAuditEvents.push(nextEvent);
        }
      }
      return currentAuditEvents.filter((e) => e.seq > afterSeq);
    }
    const res = await fetch(`${BASE_URL}/audit-events?after_seq=${afterSeq}`);
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    const data = await res.json();
    return data.items || data;
  },

  resetMockStream(): void {
    streamedIndex = 0;
    currentAuditEvents.length = 0;
    currentAuditEvents.push(...(mockAuditSeed as AuditEvent[]));
  },
};
