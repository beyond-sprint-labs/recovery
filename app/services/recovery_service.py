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
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Final, Protocol, cast

from pydantic import ValidationError

from app.agent.agent import ToolRunner
from app.agent.errors import AgentError, AgentInputError
from app.agent.schemas import AgentOutput
from app.core.config import Settings
from app.core.errors import ConflictError, NotFoundError, UnprocessableError
from app.core.schemas import (
    Actor,
    Alternative,
    AttemptedAlternative,
    AttemptedComputed,
    AuditEvent,
    CreateProposalIn,
    Currency,
    CustomerIntent,
    Invoice,
    InvoiceStatus,
    Policy,
    PolicyCheck,
    ProposalOut,
    RuleHit,
    Severity,
    TextNumberCheck,
)
from app.core.states import ProposalStatus, assert_transition
from app.finance import FinanceError, calculate_alternatives
from app.finance.engine import ENGINE_VERSION
from app.repositories.invoices_repo import InvoicesRepo
from app.repositories.proposals_repo import (
    NewProposal,
    ProposalInsertConflictError,
    ProposalRecord,
    ProposalResult,
    ProposalsRepo,
)
from app.services.audit_service import MAX_PAGE_LIMIT, AuditService
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
    ) -> None:
        self._invoices = invoices
        self._proposals = proposals
        self._audit = audit
        self._uow = uow
        self._agent_factory = agent_factory
        self._settings = settings
        self._clock = clock

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
        # Slice 3 hook: when the status is EXECUTED and last_paypal_check_at is older than
        # 10 s, reconcile lazily with PayPal here. No Slice 1 state can reach EXECUTED.
        record = self._proposals.get(proposal_id)
        if record is None:
            raise NotFoundError("PROPOSAL_NOT_FOUND", "Proposal not found")
        if record.status is ProposalStatus.DRAFTED or record.result is None:
            raise ConflictError("PROPOSAL_IN_PROGRESS", "The proposal is still being drafted")
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
        return self._finalize(proposal_id=proposal_id, invoice=invoice, decision=decision)

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

    def _finalize(self, *, proposal_id: str, invoice: Invoice, decision: _Decision) -> ProposalOut:
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
        )
