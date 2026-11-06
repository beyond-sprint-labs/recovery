"""Recovery Service (Fase A): uses stubs for unmerged modules."""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.models import ProposalRow
from app.core.schemas import (
    Actor,
    ApproveIn,
    CreateProposalIn,
    ProposalStatus,
    RespondIn,
    Severity,
)
from app.repositories.proposals_repo import ProposalsRepo
from app.services.audit_service import AuditService

# Stubs for missing modules
from app.services.stubs.agent_stub import run_agent
from app.services.stubs.execution_stub import DummyExecutionService


class RecoveryService:
    def __init__(
        self,
        repo: ProposalsRepo,
        audit: AuditService,
        execution: DummyExecutionService | Any = None,
    ) -> None:
        self._repo = repo
        self._audit = audit
        self._execution = execution or DummyExecutionService()

    def create_proposal(self, invoice_id: str, body: CreateProposalIn, idem_key: str) -> Any:
        # 1. Idempotency check
        existing = self._repo.get_by_idempotency_key(idem_key)
        if existing:
            return existing

        # 2. Run Agent (Stub)
        intent = run_agent(body.customer_message, body.scenario_id)

        # 3. Check policy / build alternatives (Simplified for Fase A)
        # In the real code, this calls finance.build_alternatives()
        # For the stub, if intent is 40%, we mark it BLOCKED.
        is_blocked = intent.requested_discount_pct == "40"

        if is_blocked:
            blocked_reasons = [
                {"code": "MAX_DISCOUNT_PCT", "limit": "15", "attempted": "40", "unit": "pct"}
            ]
            alternatives = []
        else:
            blocked_reasons = []
            alternatives = [
                {"type": "settlement_discount", "terms": {"discount_pct": "10"}, "policy_ok": True},
                {
                    "type": "down_payment_installments",
                    "terms": {"down_payment_pct": "30", "installments": 3},
                    "policy_ok": True,
                },
            ]

        # 4. Build the DB row
        proposal = ProposalRow(
            id=f"prop_{uuid.uuid4().hex[:6]}",
            invoice_id=invoice_id,
            status=ProposalStatus.DRAFTED.value,
            idempotency_key=idem_key,
            customer_intent=intent.model_dump(mode="json"),
            alternatives=alternatives,
            policy_check={"status": "PASSED" if not is_blocked else "BLOCKED", "violations": []},
            text_number_check={"status": "PASSED"},
            blocked_reasons=blocked_reasons,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self._repo.create(proposal)

        # 5. Transition DRAFTED -> BLOCKED or PENDING_MERCHANT
        final_status = ProposalStatus.BLOCKED if is_blocked else ProposalStatus.PENDING_MERCHANT
        self._repo.update_status(proposal.id, ProposalStatus.DRAFTED, final_status)

        # 6. Audit
        self._audit.record(
            actor=Actor(type="SYSTEM", id="recovery_service"),
            action="PROPOSAL_DRAFTED" if not is_blocked else "PROPOSAL_BLOCKED",
            severity=Severity.INFO if not is_blocked else Severity.CRITICAL,
            summary="Proposal drafted." if not is_blocked else "Proposal blocked by policy.",
            proposal_id=proposal.id,
            invoice_id=invoice_id,
            state_from=ProposalStatus.DRAFTED,
            state_to=final_status,
            paypal_called=False,
        )

        return self._repo.get_by_id(proposal.id)  # Return the updated row

    def approve_proposal(self, proposal_id: str, body: ApproveIn) -> dict:
        proposal = self._repo.get_by_id(proposal_id)
        if not proposal:
            raise ValueError("PROPOSAL_NOT_FOUND")

        if proposal.status != ProposalStatus.PENDING_MERCHANT.value:
            raise ValueError(f"INVALID_STATE: {proposal.status}")

        # Transition PENDING_MERCHANT -> APPROVED -> PENDING_CUSTOMER
        if not self._repo.update_status(
            proposal_id, ProposalStatus.PENDING_MERCHANT, ProposalStatus.APPROVED
        ):
            raise ValueError("CONCURRENT_MODIFICATION")

        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        expires_at = datetime.now(UTC) + timedelta(minutes=1440)

        self._repo.set_customer_token(proposal_id, token_hash, expires_at)
        self._repo.set_approved_alternative(proposal_id, body.alternative_type.value)
        self._repo.update_status(
            proposal_id, ProposalStatus.APPROVED, ProposalStatus.PENDING_CUSTOMER
        )

        self._audit.record(
            actor=Actor(type="MERCHANT", id="merchant"),
            action="PROPOSAL_APPROVED",
            severity=Severity.INFO,
            summary="Proposal approved.",
            proposal_id=proposal_id,
            state_from=ProposalStatus.PENDING_MERCHANT,
            state_to=ProposalStatus.PENDING_CUSTOMER,
            paypal_called=False,
        )

        return {
            "proposal_id": proposal_id,
            "customer_link": f"/customer/proposals/{raw_token}",
            "raw_token": raw_token,  # The frontend uses this for testing
        }

    def respond_to_proposal(self, proposal_id: str, raw_token: str, body: RespondIn) -> dict:
        proposal = self._repo.get_by_id(proposal_id)
        if not proposal:
            raise ValueError("PROPOSAL_NOT_FOUND")

        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        if proposal.customer_token_hash != token_hash:
            raise ValueError("INVALID_TOKEN")

        if proposal.customer_token_used_at is not None:
            raise ValueError("TOKEN_ALREADY_USED")

        if datetime.now(UTC) > proposal.customer_token_expires_at:
            self._repo.update_status(
                proposal_id, ProposalStatus.PENDING_CUSTOMER, ProposalStatus.EXPIRED
            )
            raise ValueError("TOKEN_EXPIRED")

        if not self._repo.consume_customer_token(proposal_id):
            raise ValueError("TOKEN_ALREADY_USED")

        if body.decision == "DECLINE":
            self._repo.update_status(
                proposal_id, ProposalStatus.PENDING_CUSTOMER, ProposalStatus.DECLINED
            )
            return {"status": "DECLINED"}

        # ACCEPT: Transition and execute
        self._repo.update_status(
            proposal_id, ProposalStatus.PENDING_CUSTOMER, ProposalStatus.ACCEPTED
        )

        execution_result = self._execution.execute_replacement(
            proposal_id=proposal_id,
            original_invoice_id=proposal.invoice_id,
            new_invoice_number=f"RENEG-{proposal_id}",
            new_amount="100.00",
            request_id=f"req-{proposal_id}",
        )

        # In Fase A, we trust the DummyExecutionService and move to EXECUTED
        self._repo.update_status(proposal_id, ProposalStatus.ACCEPTED, ProposalStatus.EXECUTING)
        self._repo.update_status(proposal_id, ProposalStatus.EXECUTING, ProposalStatus.EXECUTED)

        return {"status": "EXECUTED", "execution": execution_result}
