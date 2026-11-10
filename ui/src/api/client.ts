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

const getInitialUseMocks = (): boolean => {
  if (typeof window !== 'undefined') {
    const params = new URLSearchParams(window.location.search);
    if (params.has('use_mocks')) return params.get('use_mocks') !== 'false';
    const stored = window.localStorage.getItem('USE_MOCKS');
    if (stored !== null) return stored !== 'false';
  }
  return import.meta.env.VITE_USE_MOCKS !== 'false';
};

let USE_MOCKS = getInitialUseMocks();
const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';

// Internal state for mock streaming
let streamedIndex = 0;
const currentAuditEvents: AuditEvent[] = [...(mockAuditSeed as AuditEvent[])];

function delay(min = 300, max = 600): Promise<void> {
  const ms = Math.floor(Math.random() * (max - min + 1)) + min;
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// In-memory cache for GET requests with TTL (TanStack Query equivalent client-side cache)
interface CacheEntry<T> {
  data: T;
  expiry: number;
}
const requestCache = new Map<string, CacheEntry<unknown>>();

async function fetchWithRetry<T>(
  url: string,
  options?: RequestInit,
  retries = 2,
  cacheTtlMs = 0
): Promise<T> {
  const cacheKey = `${options?.method || 'GET'}:${url}`;
  if (cacheTtlMs > 0 && (!options?.method || options.method === 'GET')) {
    const cached = requestCache.get(cacheKey);
    if (cached && cached.expiry > Date.now()) {
      return cached.data as T;
    }
  }

  let attempt = 0;
  while (attempt <= retries) {
    try {
      const res = await fetch(url, options);
      if (!res.ok) {
        // Only retry on transient 5xx server errors
        if (res.status >= 500 && attempt < retries) {
          attempt++;
          await new Promise((r) => setTimeout(r, attempt * 500));
          continue;
        }
        throw new Error(`HTTP error ${res.status}`);
      }
      const data = await res.json();
      if (cacheTtlMs > 0) {
        requestCache.set(cacheKey, { data, expiry: Date.now() + cacheTtlMs });
      }
      return data;
    } catch (err) {
      if (attempt < retries) {
        attempt++;
        await new Promise((r) => setTimeout(r, attempt * 500));
      } else {
        throw err;
      }
    }
  }
  throw new Error(`Failed to fetch from ${url} after ${retries} retries`);
}

export const apiClient = {
  isMockMode(): boolean {
    return USE_MOCKS;
  },

  setMockMode(enable: boolean): void {
    USE_MOCKS = enable;
    if (typeof window !== 'undefined') {
      window.localStorage.setItem('USE_MOCKS', enable ? 'true' : 'false');
    }
  },

  async getInvoices(): Promise<Invoice[]> {
    if (USE_MOCKS) {
      await delay();
      return mockInvoices as Invoice[];
    }
    // 30-second TTL cache prevents redundant network storms on tab navigation
    return fetchWithRetry<Invoice[]>(`${BASE_URL}/invoices`, undefined, 2, 30_000);
  },

  async createProposal(invoiceId: string, scenario: 'STANDARD' | 'BLOCKED' = 'STANDARD'): Promise<Proposal> {
    if (USE_MOCKS) {
      await delay();
      if (scenario === 'BLOCKED') {
        return mockProposalBlocked as unknown as Proposal;
      }
      return mockProposalPending as unknown as Proposal;
    }
    const idempotencyKey = `prop-req-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
    return fetchWithRetry<Proposal>(`${BASE_URL}/invoices/${invoiceId}/proposals`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Idempotency-Key': idempotencyKey,
      },
      body: JSON.stringify({
        customer_message: 'Customer requested manageable settlement options for overdue invoice.',
        scenario_id: scenario === 'BLOCKED' ? 'scen_blocked_discount' : 'scen_standard_repay',
      }),
    });
  },

  async approve(proposalId: string, req: ApproveRequest): Promise<ApproveResponse> {
    if (USE_MOCKS) {
      await delay();
      const res = { ...mockApproveResponse } as unknown as ApproveResponse;
      res.proposal_id = proposalId;
      return res;
    }
    return fetchWithRetry<ApproveResponse>(`${BASE_URL}/proposals/${proposalId}/approve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });
  },

  async getCustomerProposal(token: string): Promise<CustomerProposalView> {
    if (USE_MOCKS) {
      await delay();
      return mockCustomerProposal as unknown as CustomerProposalView;
    }
    // Cache for 15s to prevent re-querying identical proposal token on tab re-focus
    return fetchWithRetry<CustomerProposalView>(`${BASE_URL}/customer/proposals/${token}`, undefined, 2, 15_000);
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
    return fetchWithRetry<CustomerRespondResponse>(`${BASE_URL}/customer/proposals/${token}/respond`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });
  },

  async reconcile(proposalId: string): Promise<{ proposal_id: string; status: string }> {
    if (USE_MOCKS) {
      await delay();
      return { proposal_id: proposalId, status: 'RECONCILED' };
    }
    return fetchWithRetry<{ proposal_id: string; status: string }>(`${BASE_URL}/proposals/${proposalId}/reconcile`, {
      method: 'POST',
    });
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
    const data = await fetchWithRetry<{ items?: AuditEvent[] } | AuditEvent[]>(
      `${BASE_URL}/audit-events?after_seq=${afterSeq}`
    );
    return (data as { items?: AuditEvent[] }).items || (data as AuditEvent[]);
  },

  resetMockStream(): void {
    streamedIndex = 0;
    currentAuditEvents.length = 0;
    currentAuditEvents.push(...(mockAuditSeed as AuditEvent[]));
  },
};
