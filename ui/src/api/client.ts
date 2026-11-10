import type {
  ApproveIn,
  ApproveOut,
  AuditEventsPage,
  CreateProposalIn,
  CustomerProposalView,
  Invoice,
  Policy,
  ProposalOut,
  ReconcileOut,
  RejectIn,
  RejectOut,
  RespondIn,
  RespondOut,
} from "../types/api";

const API_BASE: string =
  (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000/api/v1";
const USE_MOCKS: boolean = (import.meta.env.VITE_USE_MOCKS as string | undefined) === "true";

const MOCK_LATENCY_MIN_MS = 300;
const MOCK_LATENCY_MAX_MS = 600;

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function mockLatency(): Promise<void> {
  const span = MOCK_LATENCY_MAX_MS - MOCK_LATENCY_MIN_MS;
  await delay(MOCK_LATENCY_MIN_MS + Math.random() * span);
}

async function readJson<T>(path: string): Promise<T> {
  const mod = await import(/* @vite-ignore */ path);
  // Vite JSON imports come as { default: ... }
  return (mod.default ?? mod) as T;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  
  if (!res.ok) {
    try {
      const body = await res.json();
      // Extraemos el mensaje del backend de FastAPI
      const msg = body?.error?.message || body?.detail || `Error ${res.status}`;
      throw new Error(msg);
    } catch (e) {
      throw new Error(`${res.status} ${res.statusText}`);
    }
  }
  if (res.status === 204) {
    return undefined as unknown as T;
  }
  return (await res.json()) as T;
}

function uuid(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  // Minimal RFC4122 v4 fallback
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

// ---------- State for mock audit stream ----------
let mockAuditCursor = 0;
let mockStreamItems: import("../types/api").AuditEvent[] = [];
let mockStreamLoaded = false;
let mockProposalCounter = 0;
const mockProposalRegistry: Record<string, ProposalOut> = {};
const mockInvoiceToProposal: Record<string, string> = {};

async function ensureStreamLoaded(): Promise<void> {
  if (mockStreamLoaded) return;
  const seed = await readJson<AuditEventsPage>("../mocks/audit_events.seed.json");
  const stream = await readJson<{ items: import("../types/api").AuditEvent[] }>(
    "../mocks/audit_events.stream.json",
  );
  mockStreamItems = [...seed.items, ...stream.items];
  mockAuditCursor = seed.next_seq;
  mockStreamLoaded = true;
}

// ---------- Public API ----------

export async function getHealth(): Promise<{ status: string; demo_mode: boolean }> {
  if (USE_MOCKS) {
    await mockLatency();
    return { status: "ok", demo_mode: true };
  }
  return request("/health");
}

export async function getInvoices(): Promise<Invoice[]> {
  if (USE_MOCKS) {
    await mockLatency();
    return readJson<Invoice[]>("../mocks/invoices.json");
  }
  return request<Invoice[]>("/invoices");
}

export async function getInvoice(id: string): Promise<Invoice> {
  if (USE_MOCKS) {
    await mockLatency();
    const invoices = await readJson<Invoice[]>("../mocks/invoices.json");
    const inv = invoices.find((i) => i.id === id);
    if (!inv) throw new Error(`Invoice ${id} not found`);
    return inv;
  }
  return request<Invoice>(`/invoices/${encodeURIComponent(id)}`);
}

export async function getPolicy(): Promise<Policy> {
  if (USE_MOCKS) {
    await mockLatency();
    return readJson<Policy>("../mocks/policy.json");
  }
  return request<Policy>("/policy");
}

export async function createProposal(
  invoiceId: string,
  body: CreateProposalIn,
): Promise<ProposalOut> {
  if (USE_MOCKS) {
    await mockLatency();
    const scenario = body.scenario_id ?? "";
    let file: string;
    if (scenario === "S03_exceeds_discount") file = "../mocks/proposal_blocked.json";
    else if (scenario === "S11_text_mismatch") file = "../mocks/proposal_text_mismatch.json";
    else file = "../mocks/proposal_pending.json";

    const base = await readJson<ProposalOut>(file);
    mockProposalCounter += 1;
    const suffix = mockProposalCounter.toString().padStart(2, "0");
    const proposal: ProposalOut = JSON.parse(JSON.stringify(base));
    proposal.proposal_id = `prop_mock_${suffix}`;
    proposal.invoice_id = invoiceId;
    mockProposalRegistry[proposal.proposal_id] = proposal;
    mockInvoiceToProposal[invoiceId] = proposal.proposal_id;
    return proposal;
  }

  return request<ProposalOut>(`/invoices/${encodeURIComponent(invoiceId)}/proposals`, {
    method: "POST",
    headers: { "Idempotency-Key": uuid() },
    body: JSON.stringify(body),
  });
}

export async function getProposal(id: string): Promise<ProposalOut> {
  if (USE_MOCKS) {
    await mockLatency();
    const known = mockProposalRegistry[id];
    if (known) return known;
    // Fallback: any fresh proposal for testing deep links
    const pending = await readJson<ProposalOut>("../mocks/proposal_pending.json");
    pending.proposal_id = id;
    mockProposalRegistry[id] = pending;
    return pending;
  }
  return request<ProposalOut>(`/proposals/${encodeURIComponent(id)}`);
}

export async function approveProposal(id: string, body: ApproveIn): Promise<ApproveOut> {
  if (USE_MOCKS) {
    await mockLatency();
    const base = await readJson<ApproveOut>("../mocks/approve_response.json");
    const out: ApproveOut = JSON.parse(JSON.stringify(base));
    out.proposal_id = id;
    out.approved_alternative = body.alternative_type;
    return out;
  }
  return request<ApproveOut>(`/proposals/${encodeURIComponent(id)}/approve`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function rejectProposal(id: string, body: RejectIn): Promise<RejectOut> {
  if (USE_MOCKS) {
    await mockLatency();
    return {
      proposal_id: id,
      status: "REJECTED",
      audit_events: [],
    };
  }
  return request<RejectOut>(`/proposals/${encodeURIComponent(id)}/reject`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function getCustomerProposal(token: string): Promise<CustomerProposalView> {
  if (USE_MOCKS) {
    await mockLatency();
    const view = await readJson<CustomerProposalView>("../mocks/customer_proposal.json");
    return { ...view };
  }
  return request<CustomerProposalView>(`/customer/proposals/${encodeURIComponent(token)}`);
}

export async function respondAsCustomer(
  token: string,
  body: RespondIn,
): Promise<RespondOut> {
  if (USE_MOCKS) {
    await mockLatency();
    if (body.decision === "DECLINE") {
      return {
        proposal_id: "prop_mock",
        status: "DECLINED",
        paypal: null,
        audit_events: [],
      };
    }
    return readJson<RespondOut>("../mocks/execute_response.json");
  }
  return request<RespondOut>(`/customer/proposals/${encodeURIComponent(token)}/respond`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function reconcileProposal(id: string): Promise<ReconcileOut> {
  if (USE_MOCKS) {
    await mockLatency();
    return { proposal_id: id, status: "EXECUTED", audit_events: [] };
  }
  return request<ReconcileOut>(`/proposals/${encodeURIComponent(id)}/reconcile`, {
    method: "POST",
  });
}

export async function sandboxRecordPayment(id: string): Promise<ReconcileOut> {
  if (USE_MOCKS) {
    await mockLatency();
    return { proposal_id: id, status: "PAID", audit_events: [] };
  }
  return request<ReconcileOut>(`/proposals/${encodeURIComponent(id)}/sandbox/record-payment`, {
    method: "POST",
  });
}

/**
 * Incremental polling for the live audit grid.
 * In mock mode, returns one new event per call to simulate a live stream.
 */
export async function getAuditEvents(afterSeq: number): Promise<AuditEventsPage> {
  if (USE_MOCKS) {
    await ensureStreamLoaded();
    await mockLatency();

    // Serve items with seq > afterSeq. On first call (afterSeq=0) return the seed.
    const items = mockStreamItems.filter((e) => e.seq > afterSeq);
    const next_seq = items.length ? items[items.length - 1].seq : afterSeq;
    return { items, next_seq };
  }
  return request<AuditEventsPage>(
    `/audit-events?after_seq=${afterSeq}&limit=200`,
  );
}

export const isMockMode = (): boolean => USE_MOCKS;