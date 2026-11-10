import type { PayPalStep } from "../types/api";

const STEP_LABEL: Record<string, string> = {
  preflight: "Preflight check",
  draft_created: "Draft created",
  original_cancelled: "Original cancelled",
  invoice_sent: "Invoice sent",
  webhook_received: "Webhook received",
};

export function ExecutionTimeline({ steps }: { steps: PayPalStep[] }) {
  return (
    <ol className="timeline">
      {steps.map((s) => (
        <li key={s.name} className={`timeline-step timeline-${s.status.toLowerCase()}`}>
          <span className="dot" />
          <span className="label">{STEP_LABEL[s.name] ?? s.name}</span>
          {s.ref ? <span className="ref">{s.ref}</span> : null}
        </li>
      ))}
    </ol>
  );
}