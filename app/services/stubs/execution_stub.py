"""Stub for F1-18 (Execution Service). Replaced when the real one is merged."""

from app.core.schemas import ProposalStatus


class DummyExecutionService:
    def execute_replacement(self, **kwargs) -> dict:
        # Simulates a successful PayPal execution
        return {
            "status": ProposalStatus.EXECUTED,
            "new_invoice_id": "MOCK-INV-EXECUTED-123",
            "original_invoice_id": kwargs.get("original_invoice_id"),
            "steps": ["preflight_ok", "draft_created", "original_cancelled", "draft_sent"],
        }
