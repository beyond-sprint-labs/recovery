"""RecoveryService, F1-13 slice 1: proposal creation and read-only queries.

Flow of ``create_proposal`` (Roadmap section 4.4, steps 1-10):

1. Validate the ``Idempotency-Key`` and replay an existing proposal (409 on key reuse with
   another request, or while the first request is still running).
2. Load the invoice (must be OVERDUE) and sanitize the customer message (422 when empty).
3. Insert the proposal as ``DRAFTED`` (+ optional sanitization audit event) and COMMIT.
   The UNIQUE key makes concurrent duplicates fail at the database, not in application code.
4. Run the agent / finance engine / policy / text guard with NO transaction open.
5. Finalize with a compare-and-set ``DRAFTED -> PENDING_MERCHANT | BLOCKED`` plus exactly one
   audit event, in one transaction. ``DRAFTED`` never lingers after a normal failure:
   every pipeline error becomes a persisted ``BLOCKED`` proposal.

The service never calls PayPal in this slice (``paypal_called`` is always false).
"""

import hashlib
import json
import logging
import re
import secrets
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Final, NoReturn, Protocol, cast

from pydantic import ValidationError

from app.agent.agent import ToolRunner
from app.agent.errors import AgentError, AgentInputError
from app.agent.schemas import AgentOutput
from app.core.config import Settings
from app.core.errors import ConflictError, NotFoundError, UnprocessableError, UpstreamError
from app.core.schemas import (
    Actor,
    Alternative,
    AlternativeType,
    ApproveIn,
    ApproveOut,
    AttemptedAlternative,
    AttemptedComputed,
    AuditEvent,
    CreateProposalIn,
    Currency,
    CustomerIntent,
    Invoice,
    InvoiceStatus,
    PayPalExecution,
    Policy,
    PolicyCheck,
    ProposalOut,
    ProposalStatusOut,
    RejectIn,
    RuleHit,
    Severity,
    TextNumberCheck,
)
from app.core.states import ProposalStatus, assert_transition
from app.finance import FinanceError, calculate_alternatives
from app.finance.engine import ENGINE_VERSION
from app.finance.policy import validate as validate_policy
from app.paypal.alternatives import (
    AlternativeMappingError,
    build_replacement_request,
    confirmation_label,
    select_approved_alternative,
    simulation_notice,
)
from app.paypal.gateway import PayPalError, PayPalGateway, PayPalInvoiceState
from app.repositories.invoices_repo import InvoicesRepo, PaymentContext
from app.repositories.proposals_repo import (
    NewProposal,
    ProposalInsertConflictError,
    ProposalRecord,
    ProposalResult,
    ProposalsRepo,
)
from app.services.approval_templates import (
    build_final_message_allowed_numbers,
    render_customer_message,
)
from app.services.audit_service import MAX_PAGE_LIMIT, AuditService
from app.services.execution_service import (
    ExecutionResult,
    ExecutionService,
    ExecutionStateError,
    is_paid_in_full,
)
from app.services.input_sanitizer import sanitize_customer_message
from app.services.text_guard import AllowedNumbers, check_text_numbers

logger = logging.getLogger(__name__)

# Server-side defaults for terms the customer did not request. They are clamped to the
# merchant policy so a default can never auto-block a proposal.
DEFAULT_DISCOUNT_PCT: Final = Decimal("10")
DEFAULT_DOWN_PAYMENT_PCT: Final = Decimal("30")
DEFAULT_INSTALLMENTS: Final = 3
DEFAULT_PERIODIC_RATE_PCT: Final = Decimal("1.5")
# A 100 % down payment leaves nothing to finance; cap below it (and let policy decide).
MAX_DOWN_PAYMENT_PCT: Final = Decimal("99")

_PCT_QUANTUM: Final = Decimal("0.0001")
_IDEMPOTENCY_KEY_RE: Final = re.compile(r"[A-Za-z0-9_.:-]{1,128}")
# Lazy reconciliation asks PayPal at most once per interval and proposal (ROADMAP 4.5).
LAZY_RECONCILE_INTERVAL: Final = timedelta(seconds=10)
_MONEY_QUANTUM: Final = Decimal("0.01")

_MERCHANT_ACTOR: Final = Actor(type="MERCHANT", id="merchant_demo")
_APPROVAL_LABELS: Final = {
    AlternativeType.SETTLEMENT_DISCOUNT: "settlement discount",
    AlternativeType.DOWN_PAYMENT_INSTALLMENTS: "down payment + installments",
}


def _format_ttl(minutes: int) -> str:
    """Human-readable token lifetime for the audit trail ("24 hours", "90 minutes")."""
    if minutes % 60 == 0:
        hours = minutes // 60
        return f"{hours} hour" if hours == 1 else f"{hours} hours"
    return f"{minutes} minutes"


# --- ports ------------------------------------------------------------------------------


class UnitOfWork(Protocol):
    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class ProposalAgent(Protocol):
    """Surface shared by ``NegotiationAgent`` and ``ScriptedAgent``."""

    def run(self, sanitized_message: str, tool_runner: ToolRunner) -> AgentOutput: ...

    def explain_alternatives(self, engine_result: Mapping[str, object]) -> str: ...

    def draft_customer_message(self, engine_result: Mapping[str, object]) -> str: ...


@dataclass(frozen=True, slots=True)
class AgentBinding:
    agent: ProposalAgent
    mode: str  # "DEMO" (scripted) or "LLM"
    agent_id: str = "agent_v1"


AgentFactory = Callable[[str | None], AgentBinding]
# Builds ``ExecutionService`` on demand: PayPal is only touched by the methods that need it.
ExecutionProvider = Callable[[], ExecutionService]


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


# --- pure helpers (public so they can be unit-tested) ---------------------------------------


def compute_request_hash(invoice_id: str, body: CreateProposalIn) -> str:
    """Fingerprint of the request, used to detect an Idempotency-Key reused for another one."""
    canonical = json.dumps(
        {
            "invoice_id": invoice_id,
            "customer_message": body.customer_message,
            "scenario_id": body.scenario_id,
        },
        sort_keys=True,
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _pct_text(value: Decimal) -> str:
    """Plain Pct string: no exponent, no trailing zeros ("30", "33.3333")."""
    return format(value.normalize(), "f")


def build_requested_terms(
    intent: CustomerIntent, *, balance: str, policy: Policy
) -> tuple[dict[str, object], dict[str, object]]:
    """Turn the agent's intent into concrete engine terms.

    Terms the customer explicitly requested are passed through untouched so the policy gate
    can block them (S03: 40 % discount). Terms the customer did not request default to the
    golden-case values clamped to the policy, so they can never violate it.
    """
    if intent.requested_discount_pct is not None:
        discount_pct = intent.requested_discount_pct
    else:
        discount_pct = _pct_text(min(DEFAULT_DISCOUNT_PCT, Decimal(policy.max_discount_pct)))

    total = Decimal(balance)
    if intent.available_now is not None and total > 0:
        base_down = (Decimal(intent.available_now) * Decimal(100) / total).quantize(
            _PCT_QUANTUM, rounding=ROUND_HALF_UP
        )
    else:
        base_down = DEFAULT_DOWN_PAYMENT_PCT
    down_payment_pct = min(
        max(base_down, Decimal(policy.min_down_payment_pct)), MAX_DOWN_PAYMENT_PCT
    )

    if intent.preferred_installments is not None:
        installments = intent.preferred_installments
    else:
        installments = min(DEFAULT_INSTALLMENTS, policy.max_installments)

    rate_pct = min(DEFAULT_PERIODIC_RATE_PCT, Decimal(policy.max_financing_rate_pct))

    settlement: dict[str, object] = {"discount_pct": discount_pct}
    plan: dict[str, object] = {
        "down_payment_pct": _pct_text(down_payment_pct),
        "installments": installments,
        "periodic_rate_pct": _pct_text(rate_pct),
    }
    return settlement, plan


def build_allowed_numbers(
    *,
    alternatives: Sequence[Alternative],
    intent: CustomerIntent,
    policy: Policy,
    invoice_id: str,
    balance: str,
) -> AllowedNumbers:
    """Figures a generated text may contain.

    Deliberately narrow: engine figures, schedule amounts, the terms, the intent, the
    policy parameters and the balance. Schedule indices and "small integers" are NOT added:
    membership is by numeric value, so a blanket ``1..6`` would let an invented ``$5.00`` pass.
    """
    values: set[Decimal] = {Decimal(balance)}
    for alt in alternatives:
        for figure in (
            alt.amount_due_now,
            alt.installment_amount,
            alt.total_paid,
            alt.present_value,
            alt.financing_cost,
            alt.merchant_difference_vs_balance,
        ):
            if figure is not None:
                values.add(Decimal(figure))
        for term in alt.terms.model_dump().values():
            values.add(Decimal(term) if isinstance(term, str) else Decimal(int(term)))
        for item in alt.schedule:
            values.update(
                Decimal(figure) for figure in (item.amount, item.principal, item.interest)
            )

    if intent.available_now is not None:
        values.add(Decimal(intent.available_now))
    if intent.requested_discount_pct is not None:
        values.add(Decimal(intent.requested_discount_pct))
    if intent.preferred_installments is not None:
        values.add(Decimal(intent.preferred_installments))

    values.update(
        (
            Decimal(policy.max_discount_pct),
            Decimal(policy.min_down_payment_pct),
            Decimal(policy.max_installments),
            Decimal(policy.max_financing_rate_pct),
            Decimal(policy.merchant_discount_rate_pct),
        )
    )
    return AllowedNumbers(values=frozenset(values), invoice_ids=frozenset({invoice_id}))


def policy_from_settings(settings: Settings) -> Policy:
    """Server-owned policy as the public contract (strings, no exponent)."""
    return Policy(
        currency="USD",
        max_discount_pct=format(settings.policy_max_discount_pct, "f"),
        min_down_payment_pct=format(settings.policy_min_down_payment_pct, "f"),
        max_installments=settings.policy_max_installments,
        max_financing_rate_pct=format(settings.policy_max_financing_rate_pct, "f"),
        merchant_discount_rate_pct=format(settings.merchant_discount_rate_pct, "f"),
    )


# --- decisions ----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class _Decision:
    """Outcome of the pipeline: what to persist and the one audit event to write."""

    status: ProposalStatus
    result: ProposalResult
    actor: Actor
    action: str
    severity: Severity
    summary: str
    rule: RuleHit | None = None
    proposed_by: Actor | None = None


@dataclass
class _Capture:
    engine_result: dict[str, object] | None = None


def _violation_message(hit: RuleHit) -> str:
    match hit.code:
        case "MAX_DISCOUNT_PCT":
            return f"Requested discount {hit.attempted}% exceeds merchant limit {hit.limit}%"
        case "MIN_DOWN_PAYMENT_PCT":
            return f"Down payment {hit.attempted}% is below merchant minimum {hit.limit}%"
        case "MAX_INSTALLMENTS":
            return f"Requested {hit.attempted} installments exceed merchant limit {hit.limit}"
        case "MAX_FINANCING_RATE_PCT":
            return f"Financing rate {hit.attempted}% exceeds merchant limit {hit.limit}%"
        case _:
            return f"Terms violate merchant policy rule {hit.code}"


def _violation_summary(hit: RuleHit) -> str:
    match hit.code:
        case "MAX_DISCOUNT_PCT":
            return (
                f"AI-proposed {hit.attempted}% settlement discount exceeds "
                f"merchant limit of {hit.limit}%"
            )
        case "MIN_DOWN_PAYMENT_PCT":
            return (
                f"AI-proposed {hit.attempted}% down payment is below "
                f"merchant minimum of {hit.limit}%"
            )
        case "MAX_INSTALLMENTS":
            return f"AI-proposed {hit.attempted} installments exceed merchant limit of {hit.limit}"
        case "MAX_FINANCING_RATE_PCT":
            return (
                f"AI-proposed {hit.attempted}% financing rate exceeds "
                f"merchant limit of {hit.limit}%"
            )
        case _:
            return f"AI-proposed terms violate merchant policy rule {hit.code}"


def _blocked(
    *,
    intent: CustomerIntent,
    reasons: list[RuleHit],
    actor: Actor,
    severity: Severity,
    summary: str,
    audit_rule: RuleHit | None,
    proposed_by: Actor | None,
    policy_check: PolicyCheck,
    text_check: TextNumberCheck | None = None,
    attempted: list[AttemptedAlternative] | None = None,
) -> _Decision:
    return _Decision(
        status=ProposalStatus.BLOCKED,
        result=ProposalResult(
            customer_intent=intent,
            alternatives=[],
            attempted=attempted or [],
            blocked_reasons=reasons,
            explanation=None,
            customer_message_draft=None,
            policy_check=policy_check,
            text_number_check=text_check or TextNumberCheck(status="SKIPPED"),
        ),
        actor=actor,
        action="PROPOSAL_BLOCKED",
        severity=severity,
        summary=summary,
        rule=audit_rule,
        proposed_by=proposed_by,
    )


def _failure(
    *,
    code: str,
    message: str,
    severity: Severity,
    intent: CustomerIntent,
    proposed_by: Actor | None,
) -> _Decision:
    """Pipeline failure: the policy gate did not run, so ``policy_check`` stays BLOCKED."""
    reason = RuleHit(code=code, message=message)
    return _blocked(
        intent=intent,
        reasons=[reason],
        actor=Actor(type="SYSTEM", id="recovery_service"),
        severity=severity,
        summary=f"{message}; PayPal not called",
        audit_rule=reason,
        proposed_by=proposed_by,
        policy_check=PolicyCheck(status="BLOCKED"),
    )


def _agent_failure(
    exc: Exception, *, proposal_id: str, intent: CustomerIntent, proposed_by: Actor | None
) -> _Decision:
    """Map an exception to a typed BLOCKED decision. Never leaks exception details."""
    if isinstance(exc, AgentInputError):
        return _failure(
            code="AGENT_INPUT_REJECTED",
            message="The agent rejected the customer message",
            severity=Severity.WARN,
            intent=intent,
            proposed_by=proposed_by,
        )
    if isinstance(exc, (AgentError, ValidationError)):
        return _failure(
            code="INVALID_AGENT_OUTPUT",
            message="The agent output failed contract validation",
            severity=Severity.CRITICAL,
            intent=intent,
            proposed_by=proposed_by,
        )
    if isinstance(exc, FinanceError):
        return _failure(
            code="ENGINE_ERROR",
            message="The financial engine rejected the request",
            severity=Severity.CRITICAL,
            intent=intent,
            proposed_by=proposed_by,
        )
    logger.error("Unexpected failure while drafting proposal %s", proposal_id, exc_info=exc)
    return _failure(
        code="INTERNAL_ERROR",
        message="Unexpected error while drafting the proposal",
        severity=Severity.CRITICAL,
        intent=intent,
        proposed_by=proposed_by,
    )


def _build_out(
    *,
    proposal_id: str,
    invoice_id: str,
    status: ProposalStatus,
    engine_version: str,
    currency: str,
    result: ProposalResult,
    audit_event: AuditEvent | None,
    approved_alternative: AlternativeType | None = None,
    paypal: PayPalExecution | None = None,
) -> ProposalOut:
    return ProposalOut(
        proposal_id=proposal_id,
        invoice_id=invoice_id,
        status=status,
        engine_version=engine_version,
        currency=cast(Currency, currency),
        customer_intent=result.customer_intent,
        alternatives=result.alternatives,
        attempted=result.attempted,
        blocked_reasons=result.blocked_reasons,
        explanation=result.explanation,
        customer_message_draft=result.customer_message_draft,
        policy_check=result.policy_check,
        text_number_check=result.text_number_check,
        paypal_called=result.paypal_called,
        approved_alternative=approved_alternative,
        paypal=paypal,
        audit_event=audit_event,
    )


def _make_tool_runner(
    *,
    invoice: Invoice,
    as_of: date,
    policy: Policy,
    capture: _Capture,
) -> ToolRunner:
    """Closure injected into the agent: balance, dates and policy come from the server."""
    engine_policy = policy.model_dump(exclude={"currency"})

    def run_tool(intent: CustomerIntent) -> object:
        settlement, plan = build_requested_terms(intent, balance=invoice.balance, policy=policy)
        result = calculate_alternatives(
            {
                "engine_version": ENGINE_VERSION,
                "invoice": {
                    "id": invoice.id,
                    "currency": invoice.currency,
                    "balance": invoice.balance,
                    "due_date": invoice.due_date.isoformat(),
                    "as_of_date": as_of.isoformat(),
                },
                "alternatives": [
                    {"type": "settlement_discount", **settlement},
                    {"type": "down_payment_installments", **plan},
                ],
                "policy": engine_policy,
            }
        )
        capture.engine_result = result
        return result

    return run_tool


# --- service --------------------------------------------------------------------------------------


class RecoveryService:
    def __init__(
        self,
        *,
        invoices: InvoicesRepo,
        proposals: ProposalsRepo,
        audit: AuditService,
        uow: UnitOfWork,
        agent_factory: AgentFactory,
        settings: Settings,
        clock: Callable[[], datetime] = _utc_now,
        execution_provider: ExecutionProvider | None = None,
    ) -> None:
        self._invoices = invoices
        self._proposals = proposals
        self._audit = audit
        self._uow = uow
        self._agent_factory = agent_factory
        self._settings = settings
        self._clock = clock
        self._execution_provider = execution_provider

    # --- read-only queries -------------------------------------------------------------------

    def list_invoices(self) -> list[Invoice]:
        return self._invoices.list_all()

    def get_invoice(self, invoice_id: str) -> Invoice:
        invoice = self._invoices.get(invoice_id)
        if invoice is None:
            raise NotFoundError("INVOICE_NOT_FOUND", "Invoice not found")
        return invoice

    def get_policy(self) -> Policy:
        return policy_from_settings(self._settings)

    def get_proposal(self, proposal_id: str) -> ProposalOut:
        record = self._proposals.get(proposal_id)
        if record is None:
            raise NotFoundError("PROPOSAL_NOT_FOUND", "Proposal not found")
        if record.status is ProposalStatus.DRAFTED or record.result is None:
            raise ConflictError("PROPOSAL_IN_PROGRESS", "The proposal is still being drafted")
        if self._lazy_reconcile(record):
            record = self._require_record(proposal_id)
        return self._out_from_record(record)

    # --- create ---------------------------------------------------------------------------------

    def create_proposal(
        self, invoice_id: str, body: CreateProposalIn, idempotency_key: str
    ) -> ProposalOut:
        if _IDEMPOTENCY_KEY_RE.fullmatch(idempotency_key) is None:
            raise UnprocessableError(
                "INVALID_IDEMPOTENCY_KEY",
                "Idempotency-Key must be 1-128 characters of A-Z, a-z, 0-9, '_', '.', ':' or '-'",
            )
        request_hash = compute_request_hash(invoice_id, body)

        existing = self._proposals.get_by_idempotency_key(idempotency_key)
        if existing is not None:
            return self._replay(existing, request_hash)

        invoice = self.get_invoice(invoice_id)
        if invoice.status is not InvoiceStatus.OVERDUE:
            raise ConflictError("INVOICE_NOT_OVERDUE", "Only overdue invoices can be recovered")

        sanitized = sanitize_customer_message(body.customer_message)
        if not sanitized.text:
            raise UnprocessableError(
                "EMPTY_MESSAGE", "The customer message is empty after sanitization"
            )

        # Built before any write: a misconfigured agent must not leave a DRAFTED row behind.
        binding = self._agent_factory(self._effective_scenario(body.scenario_id))
        policy = self.get_policy()
        proposal_id = f"prop_{uuid.uuid4().hex[:12]}"
        now = self._clock()

        try:
            self._proposals.add_drafted(
                NewProposal(
                    proposal_id=proposal_id,
                    invoice_id=invoice.id,
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                    customer_message=sanitized.text,
                    engine_version=ENGINE_VERSION,
                    currency=invoice.currency,
                    created_at=now,
                )
            )
            if sanitized.removed_count:
                self._audit.record(
                    actor=Actor(type="SYSTEM", id="input_sanitizer"),
                    action="INPUT_SANITIZED",
                    severity=Severity.WARN,
                    summary=(
                        f"Removed {sanitized.removed_count} hidden control/format "
                        "character(s) from the customer message"
                    ),
                    invoice_id=invoice.id,
                    proposal_id=proposal_id,
                    rule=RuleHit(
                        code="CONTROL_CHARS_STRIPPED",
                        attempted=str(sanitized.removed_count),
                        unit="chars",
                    ),
                )
            self._uow.commit()
        except ProposalInsertConflictError:
            # Lost the idempotency race: the UNIQUE constraint is the real defence.
            self._uow.rollback()
            winner = self._proposals.get_by_idempotency_key(idempotency_key)
            if winner is None:
                raise
            return self._replay(winner, request_hash)
        except Exception:
            self._uow.rollback()
            raise

        # No transaction is open from here until finalization (outbound transaction guard).
        decision = self._decide(
            proposal_id=proposal_id,
            binding=binding,
            message=sanitized.text,
            invoice=invoice,
            policy=policy,
            as_of=now.date(),
        )
        return self._finalize(
            proposal_id=proposal_id,
            invoice=invoice,
            decision=decision,
            fallback_used=bool(getattr(binding.agent, "fallback_used", False)),
        )

        # --- merchant decision: approve / reject (F1-13 slice 2) ------------------------------

    def approve_proposal(self, proposal_id: str, body: ApproveIn) -> ApproveOut:
        """Approve ONE alternative and issue the single-use customer link (DEC-28).

        Everything happens in one transaction with no outbound call: a compare-and-set
        ``PENDING_MERCHANT -> PENDING_CUSTOMER`` plus the ``PROPOSAL_APPROVED`` and
        ``CUSTOMER_LINK_ISSUED`` audit events. The clear token exists only in the returned
        link; the database keeps its SHA-256 hash.
        """
        record = self._require_record(proposal_id)
        self._require_pending_merchant(record, "approved")
        alternative = self._offered_alternative(record, body.alternative_type)
        now = self._clock()

        message = render_customer_message(invoice_id=record.invoice_id, alternative=alternative)
        check = check_text_numbers(
            [message],
            build_final_message_allowed_numbers(
                alternative=alternative, invoice_id=record.invoice_id
            ),
        )
        if check.status != "PASSED":
            self._block_final_message(record=record, check=check, now=now)

        assert_transition(ProposalStatus.PENDING_MERCHANT, ProposalStatus.APPROVED)
        assert_transition(ProposalStatus.APPROVED, ProposalStatus.PENDING_CUSTOMER)

        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        ttl_minutes = self._settings.customer_token_ttl_min
        expires_at = now + timedelta(minutes=ttl_minutes)
        note = self._clean_note(body.note)
        label = _APPROVAL_LABELS[body.alternative_type]

        try:
            if not self._proposals.approve_pending_merchant(
                proposal_id=proposal_id,
                approved_alternative=body.alternative_type,
                token_hash=token_hash,
                token_expires_at=expires_at,
                customer_message_final=message,
                now=now,
            ):
                raise ConflictError(
                    "PROPOSAL_STATE_CONFLICT",
                    "The proposal is no longer pending merchant approval",
                )
            approved_event = self._audit.record(
                actor=_MERCHANT_ACTOR,
                action="PROPOSAL_APPROVED",
                severity=Severity.INFO,
                summary=self._with_note(f"Merchant approved the {label} option", note),
                invoice_id=record.invoice_id,
                proposal_id=proposal_id,
                state_from=ProposalStatus.PENDING_MERCHANT,
                state_to=ProposalStatus.APPROVED,
                paypal_called=False,
            )
            issued_event = self._audit.record(
                actor=Actor(type="SYSTEM", id="recovery_service"),
                action="CUSTOMER_LINK_ISSUED",
                severity=Severity.INFO,
                summary=(f"Single-use customer link issued; expires in {_format_ttl(ttl_minutes)}"),
                invoice_id=record.invoice_id,
                proposal_id=proposal_id,
                state_from=ProposalStatus.APPROVED,
                state_to=ProposalStatus.PENDING_CUSTOMER,
                paypal_called=False,
            )
            self._uow.commit()
        except Exception:
            self._uow.rollback()
            raise

        base_url = self._settings.public_base_url.rstrip("/")
        return ApproveOut(
            proposal_id=proposal_id,
            status=ProposalStatus.PENDING_CUSTOMER,
            approved_alternative=body.alternative_type,
            customer_link=f"{base_url}/customer/{token}",
            customer_token_expires_at=expires_at,
            audit_events=[approved_event, issued_event],
        )

    def reject_proposal(self, proposal_id: str, body: RejectIn) -> ProposalStatusOut:
        """Compare-and-set ``PENDING_MERCHANT -> REJECTED`` with its audit event."""
        record = self._require_record(proposal_id)
        self._require_pending_merchant(record, "rejected")
        assert_transition(ProposalStatus.PENDING_MERCHANT, ProposalStatus.REJECTED)
        note = self._clean_note(body.note)

        try:
            if not self._proposals.reject_pending_merchant(
                proposal_id=proposal_id, now=self._clock()
            ):
                raise ConflictError(
                    "PROPOSAL_STATE_CONFLICT",
                    "The proposal is no longer pending merchant approval",
                )
            event = self._audit.record(
                actor=_MERCHANT_ACTOR,
                action="PROPOSAL_REJECTED",
                severity=Severity.INFO,
                summary=self._with_note("Merchant rejected the proposal", note),
                invoice_id=record.invoice_id,
                proposal_id=proposal_id,
                state_from=ProposalStatus.PENDING_MERCHANT,
                state_to=ProposalStatus.REJECTED,
                paypal_called=False,
            )
            self._uow.commit()
        except Exception:
            self._uow.rollback()
            raise
        return ProposalStatusOut(
            proposal_id=proposal_id, status=ProposalStatus.REJECTED, audit_events=[event]
        )

    @staticmethod
    def _require_pending_merchant(record: ProposalRecord, verb: str) -> None:
        if record.status is not ProposalStatus.PENDING_MERCHANT:
            raise ConflictError(
                "PROPOSAL_NOT_PENDING_MERCHANT",
                f"Only proposals in PENDING_MERCHANT can be {verb}; "
                f"current status is {record.status.value}",
            )

    def _offered_alternative(
        self, record: ProposalRecord, alternative_type: AlternativeType
    ) -> Alternative:
        """The chosen alternative, re-checked against the CURRENT server policy (fail closed)."""
        if record.result is None:
            raise ConflictError("PROPOSAL_IN_PROGRESS", "The proposal is still being drafted")
        chosen = next(
            (alt for alt in record.result.alternatives if alt.type == alternative_type), None
        )
        if chosen is None or not chosen.policy_ok or chosen.violations:
            raise UnprocessableError(
                "ALTERNATIVE_NOT_OFFERED",
                "The chosen alternative was not offered within policy",
            )
        try:
            violations = validate_policy(chosen.terms.model_dump(), self.get_policy().model_dump())
        except FinanceError as err:
            raise UnprocessableError(
                "ALTERNATIVE_NOT_OFFERED",
                "The chosen alternative could not be validated against the merchant policy",
            ) from err
        if violations:
            raise UnprocessableError(
                "ALTERNATIVE_NOT_OFFERED",
                "The chosen alternative no longer complies with the merchant policy",
            )
        return chosen

    def _block_final_message(
        self, *, record: ProposalRecord, check: TextNumberCheck, now: datetime
    ) -> NoReturn:
        """Persist ``PENDING_MERCHANT -> BLOCKED(TEXT_NUMBER_MISMATCH)`` and answer 409 (AC12)."""
        assert_transition(ProposalStatus.PENDING_MERCHANT, ProposalStatus.BLOCKED)
        shown = ", ".join(check.unmatched)[:200]
        reason = RuleHit(
            code="TEXT_NUMBER_MISMATCH",
            attempted=shown or None,
            unit="figures",
            message="The approval message contains figures the finance engine did not produce",
        )
        try:
            if not self._proposals.block_pending_merchant(
                proposal_id=record.proposal_id, reasons=[reason], text_check=check, now=now
            ):
                raise ConflictError(
                    "PROPOSAL_STATE_CONFLICT",
                    "The proposal is no longer pending merchant approval",
                )
            self._audit.record(
                actor=Actor(type="SYSTEM", id="text_guard"),
                action="PROPOSAL_BLOCKED",
                severity=Severity.CRITICAL,
                summary=(
                    "Approval message contains figures not produced by the finance engine "
                    f"({shown}); PayPal not called"
                ),
                invoice_id=record.invoice_id,
                proposal_id=record.proposal_id,
                state_from=ProposalStatus.PENDING_MERCHANT,
                state_to=ProposalStatus.BLOCKED,
                rule=reason,
                paypal_called=False,
            )
            self._uow.commit()
        except Exception:
            self._uow.rollback()
            raise
        raise ConflictError(
            "TEXT_NUMBER_MISMATCH",
            "The approval message failed the text-number check; the proposal is now blocked",
        )

    @staticmethod
    def _clean_note(note: str | None) -> str | None:
        """Merchant notes are free text that lands in the audit trail: strip hidden characters."""
        if note is None:
            return None
        return sanitize_customer_message(note).text or None

    @staticmethod
    def _with_note(summary: str, note: str | None) -> str:
        return f"{summary}. Merchant note: {note}" if note else summary

    # --- PayPal execution, reconciliation and payment confirmation (F1-18b) ---------------

    def run_execution(self, proposal_id: str) -> ExecutionResult:
        """Run the anti-double-charge replacement for a proposal already in EXECUTING.

        Slice 3 hook: ``respond`` commits ACCEPTED -> EXECUTING and then calls this. The read
        transaction is closed before any PayPal call (invariant 5); every step is persisted by
        the journal in its own transaction.
        """
        execution = self._execution()
        record = self._require_record(proposal_id)
        if record.status is not ProposalStatus.EXECUTING:
            raise ConflictError("PROPOSAL_NOT_EXECUTING", "The proposal is not in EXECUTING state")
        alternative = self._approved_alternative(record)
        context = self._payment_context(record)
        original_invoice_id = self._original_paypal_id(context)
        try:
            request = build_replacement_request(
                proposal_id=record.proposal_id,
                alternative=alternative,
                recipient_email=context.recipient_email,
            )
        except AlternativeMappingError as err:
            raise UnprocessableError(err.code, err.message) from err
        request_id = (
            record.execution.request_id if record.execution else f"req_{record.proposal_id}"
        )

        self._uow.rollback()  # invariant 5: no transaction open during PayPal calls
        try:
            return execution.execute_replacement(
                proposal_id=record.proposal_id,
                original_invoice_id=original_invoice_id,
                new_invoice_number=request.invoice_number,
                new_amount=request.amount,
                recipient_email=context.recipient_email,
                request_id=request_id,
            )
        except ExecutionStateError as err:
            raise ConflictError("EXECUTION_STATE_CONFLICT", str(err)) from err

    def reconcile_proposal(self, proposal_id: str) -> ProposalStatusOut:
        """Resume NEEDS_RECONCILIATION from live PayPal state. Never cancels (DEC-27).

        A FAILED proposal that still owns an orphan draft is also accepted: only that draft is
        deleted and the proposal stays FAILED.
        """
        execution = self._execution()
        record = self._require_record(proposal_id)
        has_orphan_draft = (
            record.status is ProposalStatus.FAILED
            and record.execution is not None
            and record.execution.draft_id is not None
        )
        if record.status is not ProposalStatus.NEEDS_RECONCILIATION and not has_orphan_draft:
            raise ConflictError(
                "PROPOSAL_NOT_RECONCILABLE",
                "Only proposals in NEEDS_RECONCILIATION, or FAILED with an orphan draft, "
                "can be reconciled",
            )
        original_invoice_id = self._original_paypal_id(self._payment_context(record))
        last_seq = self._last_audit_seq(proposal_id)

        self._uow.rollback()  # invariant 5: no transaction open during PayPal calls
        try:
            if has_orphan_draft:
                result = execution.cleanup_orphan_draft(
                    proposal_id=proposal_id, original_invoice_id=original_invoice_id
                )
            else:
                result = execution.reconcile(
                    proposal_id=proposal_id, original_invoice_id=original_invoice_id
                )
        except ExecutionStateError as err:
            raise ConflictError("EXECUTION_STATE_CONFLICT", str(err)) from err
        return ProposalStatusOut(
            proposal_id=proposal_id,
            status=result.status,
            audit_events=self._events_since(proposal_id, last_seq),
        )

    def record_sandbox_payment(self, proposal_id: str) -> ProposalStatusOut:
        """Sandbox-only shortcut: record the payment in PayPal, then confirm it.

        The amount comes from the persisted approved alternative, never from the request. The
        move to PAID uses the same compare-and-set as the webhook, so whoever arrives second
        is a harmless no-op.
        """
        if not self._sandbox_shortcut_enabled():
            raise NotFoundError(
                "SANDBOX_SHORTCUT_DISABLED", "The Sandbox payment shortcut is not enabled"
            )
        execution = self._execution()
        record = self._require_record(proposal_id)
        if record.status is not ProposalStatus.EXECUTED:
            raise ConflictError(
                "PROPOSAL_NOT_EXECUTED", "Payments can only be recorded for an EXECUTED proposal"
            )
        draft_id, alternative = self._payment_target(record)
        expected = alternative.amount_due_now
        last_seq = self._last_audit_seq(proposal_id)

        self._uow.rollback()  # invariant 5: no transaction open during PayPal calls
        gateway = execution.gateway
        state = self._read_invoice(gateway, draft_id)
        if not self._same_amount(state.total_amount, expected):
            raise ConflictError(
                "PAYMENT_AMOUNT_MISMATCH",
                "The PayPal invoice total differs from the approved amount",
            )
        if not is_paid_in_full(state, expected):
            try:
                gateway.record_payment(draft_id, self._remaining_amount(state, expected))
            except PayPalError as err:
                raise UpstreamError(err.code, err.message) from err
            state = self._read_invoice(gateway, draft_id)
        if is_paid_in_full(state, expected):
            summary = self._confirmation_summary(alternative, draft_id, sandbox_shortcut=True)
            self._confirm_payment(record=record, draft_id=draft_id, summary=summary)
        current = self._require_record(proposal_id)
        return ProposalStatusOut(
            proposal_id=proposal_id,
            status=current.status,
            audit_events=self._events_since(proposal_id, last_seq),
        )

    def _lazy_reconcile(self, record: ProposalRecord) -> bool:
        """Ask PayPal whether an EXECUTED proposal was paid (ROADMAP 4.5).

        Returns True when PayPal was asked, so the caller re-reads the row. PayPal failures
        never break the GET: the check is throttled and retried on a later request.
        """
        if self._execution_provider is None or record.status is not ProposalStatus.EXECUTED:
            return False
        last = record.last_paypal_check_at
        if last is not None and self._clock() - last <= LAZY_RECONCILE_INTERVAL:
            return False
        try:
            draft_id, alternative = self._payment_target(record)
        except (ConflictError, UnprocessableError):
            return False

        self._uow.rollback()  # invariant 5: no transaction open during PayPal calls
        paid = False
        try:
            state = self._execution().gateway.get_invoice(draft_id)
            paid = is_paid_in_full(state, alternative.amount_due_now)
        except (PayPalError, UpstreamError) as err:
            logger.warning(
                "Lazy PayPal check failed for proposal %s: %s",
                record.proposal_id,
                getattr(err, "code", type(err).__name__),
            )
        if paid:
            summary = self._confirmation_summary(alternative, draft_id, sandbox_shortcut=False)
            self._confirm_payment(record=record, draft_id=draft_id, summary=summary)
        else:
            self._touch_paypal_check(record.proposal_id)
        return True

    def _confirm_payment(self, *, record: ProposalRecord, draft_id: str, summary: str) -> bool:
        """CAS EXECUTED -> PAID plus PAYMENT_CONFIRMED in one transaction.

        Returns False when another path (webhook, another check) already moved the proposal.
        """
        assert_transition(ProposalStatus.EXECUTED, ProposalStatus.PAID)
        try:
            if not self._proposals.mark_paid(proposal_id=record.proposal_id, now=self._clock()):
                self._uow.rollback()
                return False
            self._audit.record(
                actor=Actor(type="PAYPAL", id="paypal_invoicing"),
                action="PAYMENT_CONFIRMED",
                severity=Severity.INFO,
                summary=summary,
                invoice_id=record.invoice_id,
                proposal_id=record.proposal_id,
                state_from=ProposalStatus.EXECUTED,
                state_to=ProposalStatus.PAID,
                paypal_called=True,
                source="RECONCILIATION",
                paypal_ref=draft_id,
            )
            self._uow.commit()
        except Exception:
            self._uow.rollback()
            raise
        return True

    def _touch_paypal_check(self, proposal_id: str) -> None:
        try:
            self._proposals.touch_paypal_check(proposal_id=proposal_id, now=self._clock())
            self._uow.commit()
        except Exception:
            self._uow.rollback()
            raise

    @staticmethod
    def _confirmation_summary(
        alternative: Alternative, draft_id: str, *, sandbox_shortcut: bool
    ) -> str:
        label = confirmation_label(alternative.type)
        prefix = "Merchant-recorded payment (Sandbox): " if sandbox_shortcut else ""
        summary = f"{prefix}{label} on PayPal invoice {draft_id}"
        notice = simulation_notice(alternative.type)
        return f"{summary}. {notice}" if notice else summary

    def _sandbox_shortcut_enabled(self) -> bool:
        return (
            self._settings.allow_sandbox_payment_shortcut
            and "sandbox" in self._settings.paypal_base_url.lower()
        )

    def _execution(self) -> ExecutionService:
        if self._execution_provider is None:
            raise RuntimeError("RecoveryService was built without a PayPal execution provider")
        return self._execution_provider()

    def _require_record(self, proposal_id: str) -> ProposalRecord:
        record = self._proposals.get(proposal_id)
        if record is None:
            raise NotFoundError("PROPOSAL_NOT_FOUND", "Proposal not found")
        return record

    def _approved_alternative(self, record: ProposalRecord) -> Alternative:
        if record.result is None:
            raise ConflictError("PROPOSAL_IN_PROGRESS", "The proposal is still being drafted")
        try:
            return select_approved_alternative(
                record.result.alternatives, record.approved_alternative
            )
        except AlternativeMappingError as err:
            raise UnprocessableError(err.code, err.message) from err

    def _payment_target(self, record: ProposalRecord) -> tuple[str, Alternative]:
        """PayPal id of the sent replacement invoice and the alternative it bills."""
        execution = record.execution
        if execution is None or not execution.new_sent or execution.draft_id is None:
            raise ConflictError("EXECUTION_INCOMPLETE", "The replacement invoice was never sent")
        return execution.draft_id, self._approved_alternative(record)

    def _payment_context(self, record: ProposalRecord) -> PaymentContext:
        context = self._invoices.get_payment_context(record.invoice_id)
        if context is None:
            raise NotFoundError("INVOICE_NOT_FOUND", "Invoice not found")
        return context

    @staticmethod
    def _original_paypal_id(context: PaymentContext) -> str:
        if not context.paypal_invoice_id:
            raise ConflictError(
                "INVOICE_NOT_LINKED_TO_PAYPAL", "The invoice has no PayPal invoice to replace"
            )
        return context.paypal_invoice_id

    @staticmethod
    def _read_invoice(gateway: PayPalGateway, invoice_id: str) -> PayPalInvoiceState:
        try:
            return gateway.get_invoice(invoice_id)
        except PayPalError as err:
            raise UpstreamError(err.code, err.message) from err

    @staticmethod
    def _same_amount(reported: str | None, expected: str) -> bool:
        if reported is None:
            return False
        try:
            return Decimal(reported) == Decimal(expected)
        except InvalidOperation:
            return False

    @staticmethod
    def _remaining_amount(state: PayPalInvoiceState, expected: str) -> str:
        """Server-side amount still unpaid on the replacement invoice, as a Money string."""
        try:
            paid = Decimal(state.paid_amount) if state.paid_amount is not None else Decimal("0")
            remaining = Decimal(expected) - paid
        except InvalidOperation as err:
            raise ConflictError(
                "PAYMENT_STATE_UNEXPECTED", "PayPal reported an unreadable paid amount"
            ) from err
        if remaining <= Decimal("0"):
            raise ConflictError(
                "PAYMENT_STATE_UNEXPECTED", "PayPal reports the amount as paid but not settled"
            )
        return format(remaining.quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP), "f")

    def _last_audit_seq(self, proposal_id: str) -> int:
        page = self._audit.list_events(after_seq=0, limit=MAX_PAGE_LIMIT, proposal_id=proposal_id)
        return page.next_seq

    def _events_since(self, proposal_id: str, after_seq: int) -> list[AuditEvent]:
        page = self._audit.list_events(
            after_seq=after_seq, limit=MAX_PAGE_LIMIT, proposal_id=proposal_id
        )
        return page.items

    # --- internals ------------------------------------------------------------------------------

    def _effective_scenario(self, scenario_id: str | None) -> str | None:
        """``scenario_id`` is honoured only in scripted mode or when explicitly allowed."""
        if scenario_id is None:
            return None
        if self._settings.agent_mode == "scripted" or self._settings.allow_scenario_id:
            return scenario_id
        return None

    def _decide(
        self,
        *,
        proposal_id: str,
        binding: AgentBinding,
        message: str,
        invoice: Invoice,
        policy: Policy,
        as_of: date,
    ) -> _Decision:
        """Run agent, engine, policy gate and text guard. Never raises."""
        capture = _Capture()
        runner = _make_tool_runner(invoice=invoice, as_of=as_of, policy=policy, capture=capture)
        proposed_by = Actor(type="AGENT", id=binding.agent_id, mode=binding.mode)

        try:
            output = binding.agent.run(message, runner)
        except Exception as exc:
            return _agent_failure(
                exc, proposal_id=proposal_id, intent=CustomerIntent(), proposed_by=proposed_by
            )
        intent = output.intent

        raw = capture.engine_result
        if raw is None:
            reason = RuleHit(
                code="CLARIFICATION_REQUIRED",
                message=(
                    "The customer message has no concrete payment request; "
                    "ask the customer to clarify"
                ),
            )
            return _blocked(
                intent=intent,
                reasons=[reason],
                actor=Actor(type="SYSTEM", id="recovery_service"),
                severity=Severity.WARN,
                summary="Customer message needs clarification; no alternatives drafted; "
                "PayPal not called",
                audit_rule=reason,
                proposed_by=proposed_by,
                policy_check=PolicyCheck(status="BLOCKED"),
            )

        try:
            alternatives = [
                Alternative.model_validate(item) for item in cast(list[object], raw["alternatives"])
            ]
        except (KeyError, TypeError, ValidationError):
            logger.error("Engine result for proposal %s broke the contract", proposal_id)
            return _failure(
                code="ENGINE_ERROR",
                message="The financial engine returned an invalid result",
                severity=Severity.CRITICAL,
                intent=intent,
                proposed_by=proposed_by,
            )

        violating = [alt for alt in alternatives if not alt.policy_ok]
        if violating:
            hits = [hit for alt in violating for hit in alt.violations]
            if not hits:  # policy_ok=False without a violation is an engine bug: fail closed.
                hits = [RuleHit(code="POLICY_VIOLATION")]
            return _blocked(
                intent=intent,
                reasons=[
                    hit.model_copy(update={"message": _violation_message(hit)}) for hit in hits
                ],
                actor=Actor(type="SYSTEM", id="policy_engine"),
                severity=Severity.CRITICAL,
                summary=f"{_violation_summary(hits[0])}"
                f"{f' (+{len(hits) - 1} more)' if len(hits) > 1 else ''}; PayPal not called",
                audit_rule=hits[0],
                proposed_by=proposed_by,
                policy_check=PolicyCheck(status="BLOCKED", violations=hits),
                attempted=[
                    AttemptedAlternative(
                        type=alt.type,
                        terms=alt.terms,
                        computed=AttemptedComputed(
                            amount_due_now=alt.amount_due_now,
                            merchant_difference_vs_balance=alt.merchant_difference_vs_balance,
                        ),
                    )
                    for alt in violating
                ],
            )

        try:
            explanation = binding.agent.explain_alternatives(raw)
            draft = binding.agent.draft_customer_message(raw)
            check = check_text_numbers(
                [explanation, draft],
                build_allowed_numbers(
                    alternatives=alternatives,
                    intent=intent,
                    policy=policy,
                    invoice_id=invoice.id,
                    balance=invoice.balance,
                ),
            )
        except Exception as exc:
            return _agent_failure(
                exc, proposal_id=proposal_id, intent=intent, proposed_by=proposed_by
            )

        if check.status != "PASSED":
            shown = ", ".join(check.unmatched)[:200]
            reason = RuleHit(
                code="TEXT_NUMBER_MISMATCH",
                attempted=shown or None,
                unit="figures",
                message="Generated text contains figures the finance engine did not produce",
            )
            return _blocked(
                intent=intent,
                reasons=[reason],
                actor=Actor(type="SYSTEM", id="text_guard"),
                severity=Severity.CRITICAL,
                summary=f"AI-generated text contains figures not produced by the finance "
                f"engine ({shown}); PayPal not called",
                audit_rule=reason,
                proposed_by=proposed_by,
                policy_check=PolicyCheck(status="PASSED"),
                text_check=check,
            )

        return _Decision(
            status=ProposalStatus.PENDING_MERCHANT,
            result=ProposalResult(
                customer_intent=intent,
                alternatives=alternatives,
                attempted=[],
                blocked_reasons=[],
                explanation=explanation,
                customer_message_draft=draft,
                policy_check=PolicyCheck(status="PASSED"),
                text_number_check=check,
            ),
            actor=Actor(type="SYSTEM", id="recovery_service"),
            action="PROPOSAL_DRAFTED",
            severity=Severity.INFO,
            summary=f"{len(alternatives)} alternatives drafted within policy; "
            "awaiting merchant approval",
        )

    def _finalize(
        self,
        *,
        proposal_id: str,
        invoice: Invoice,
        decision: _Decision,
        fallback_used: bool = False,
    ) -> ProposalOut:
        """Compare-and-set DRAFTED -> final state and the audit event, atomically."""
        assert_transition(ProposalStatus.DRAFTED, decision.status)
        try:
            updated = self._proposals.finalize_drafted(
                proposal_id=proposal_id,
                status=decision.status,
                result=decision.result,
                now=self._clock(),
            )
            if not updated:
                raise ConflictError(
                    "PROPOSAL_STATE_CONFLICT",
                    "The proposal is no longer in DRAFTED state",
                )

            if fallback_used:
                self._audit.record(
                    actor=Actor(type="SYSTEM", id="llm_fallback"),
                    action="LLM_FALLBACK_ACTIVATED",
                    severity=Severity.WARN,
                    summary=("LLM output unavailable or invalid; deterministic fallback activated"),
                    invoice_id=invoice.id,
                    proposal_id=proposal_id,
                    paypal_called=False,
                )

            event = self._audit.record(
                actor=decision.actor,
                action=decision.action,
                severity=decision.severity,
                summary=decision.summary,
                invoice_id=invoice.id,
                proposal_id=proposal_id,
                state_from=ProposalStatus.DRAFTED,
                state_to=decision.status,
                rule=decision.rule,
                proposed_by=decision.proposed_by,
                paypal_called=False,
            )
            self._uow.commit()
        except Exception:
            self._uow.rollback()
            raise
        return _build_out(
            proposal_id=proposal_id,
            invoice_id=invoice.id,
            status=decision.status,
            engine_version=ENGINE_VERSION,
            currency=invoice.currency,
            result=decision.result,
            audit_event=event,
        )

    def _replay(self, record: ProposalRecord, request_hash: str) -> ProposalOut:
        if record.request_hash != request_hash:
            raise ConflictError(
                "IDEMPOTENCY_KEY_REUSED",
                "This Idempotency-Key was already used with a different request",
            )
        if record.status is ProposalStatus.DRAFTED or record.result is None:
            raise ConflictError(
                "IDEMPOTENCY_IN_PROGRESS",
                "A request with this Idempotency-Key is still being processed",
            )
        return self._out_from_record(record)

    def _out_from_record(self, record: ProposalRecord) -> ProposalOut:
        assert record.result is not None  # callers check; kept for type narrowing
        page = self._audit.list_events(
            after_seq=0, limit=MAX_PAGE_LIMIT, proposal_id=record.proposal_id
        )
        return _build_out(
            proposal_id=record.proposal_id,
            invoice_id=record.invoice_id,
            status=record.status,
            engine_version=record.engine_version,
            currency=record.currency,
            result=record.result,
            audit_event=page.items[-1] if page.items else None,
            approved_alternative=record.approved_alternative,
            paypal=self._paypal_execution(record),
        )

    def _paypal_execution(self, record: ProposalRecord) -> PayPalExecution | None:
        """Execution progress for the UI, derived from the persisted journal snapshot."""
        execution = record.execution
        if execution is None:
            return None
        invoice = self._invoices.get(record.invoice_id)
        steps: list[str] = []
        if execution.draft_id is not None:
            steps.append("draft_created")
        if execution.original_cancelled:
            steps.append("original_cancelled")
        if execution.new_sent:
            steps.append("draft_sent")
        return PayPalExecution(
            new_invoice_id=execution.draft_id,
            original_invoice_id=invoice.paypal_invoice_id if invoice else None,
            steps=steps,
        )
