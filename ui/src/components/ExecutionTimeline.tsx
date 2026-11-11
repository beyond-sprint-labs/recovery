const STEP_LABEL: Record<string, string> = {
  preflight: "Preflight check",
  draft_created: "Draft created",
  original_cancelled: "Original cancelled",
  invoice_sent: "Invoice sent",
  webhook_received: "Webhook received",
};

export function ExecutionTimeline({ steps }: { steps: readonly string[] }) {
  return (
    <ol className="timeline">
      {steps.map((name, index) => (
        <li key={`${name}-${index}`} className="timeline-step timeline-ok">
          <span className="dot" />
          <span className="label">{STEP_LABEL[name] ?? name}</span>
        </li>
      ))}
    </ol>
  );
}