"""Data access for proposals. No business rules live here."""

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.models import ProposalRow
from app.core.schemas import ProposalStatus


class ProposalsRepo:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, proposal_id: str) -> ProposalRow | None:
        return self._session.get(ProposalRow, proposal_id)

    def get_by_idempotency_key(self, key: str) -> ProposalRow | None:
        stmt = select(ProposalRow).where(ProposalRow.idempotency_key == key)
        return self._session.scalars(stmt).first()

    def create(self, proposal: ProposalRow) -> None:
        self._session.add(proposal)
        self._session.flush()

    def update_status(
        self, proposal_id: str, expected_status: ProposalStatus, new_status: ProposalStatus
    ) -> bool:
        stmt = (
            update(ProposalRow)
            .where(
                ProposalRow.id == proposal_id,
                ProposalRow.status == expected_status.value,
            )
            .values(status=new_status.value, updated_at=datetime.now(UTC))
        )
        result = self._session.execute(stmt)
        return result.rowcount > 0

    def set_approved_alternative(self, proposal_id: str, alternative_type: str) -> None:
        stmt = (
            update(ProposalRow)
            .where(ProposalRow.id == proposal_id)
            .values(approved_alternative=alternative_type)
        )
        self._session.execute(stmt)

    def set_customer_token(self, proposal_id: str, token_hash: str, expires_at: datetime) -> None:
        stmt = (
            update(ProposalRow)
            .where(ProposalRow.id == proposal_id)
            .values(
                customer_token_hash=token_hash,
                customer_token_expires_at=expires_at,
            )
        )
        self._session.execute(stmt)

    def consume_customer_token(self, proposal_id: str) -> bool:
        stmt = (
            update(ProposalRow)
            .where(
                ProposalRow.id == proposal_id,
                ProposalRow.customer_token_used_at.is_(None),
            )
            .values(customer_token_used_at=datetime.now(UTC))
        )
        result = self._session.execute(stmt)
        return result.rowcount > 0

    def set_execution_field(self, proposal_id: str, key: str, value: object) -> None:
        proposal = self.get_by_id(proposal_id)
        if proposal:
            execution = dict(proposal.execution or {})
            execution[key] = value
            proposal.execution = execution
            self._session.flush()
