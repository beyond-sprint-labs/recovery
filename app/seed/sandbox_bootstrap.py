"""Explicit PayPal Sandbox preparation for a deployment.

Run once after configuring ``.env``: ``python -m app.seed.sandbox_bootstrap``. It seeds the
database and opens one original invoice per overdue seed invoice in the real PayPal Sandbox,
storing its id in ``paypal_invoice_id``. It refuses to run against anything but the Sandbox and
is safe to run again: an invoice that is already linked and open is never touched.
"""

import argparse
import json
from collections.abc import Sequence
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.core.db import Base, get_engine, get_session_factory
from app.core.models import InvoiceRow
from app.core.schemas import InvoiceStatus
from app.paypal.factory import build_gateway
from app.paypal.gateway import NewInvoiceReq, PayPalError, PayPalGateway
from app.seed.loader import seed_database

DRAFT_STATUS = "DRAFT"
OPEN_STATUSES = frozenset({"SENT", "UNPAID"})


def require_sandbox(settings: Settings) -> None:
    """Fail closed unless the configuration targets the real PayPal Sandbox with a test buyer."""
    if settings.paypal_mode != "real":
        raise SystemExit("Sandbox bootstrap requires PAYPAL_MODE=real")
    if "sandbox" not in settings.paypal_base_url:
        raise SystemExit("Sandbox bootstrap refuses to run against a non-Sandbox PayPal URL")
    if settings.paypal_sandbox_buyer_email is None:
        raise SystemExit("Sandbox bootstrap requires PAYPAL_SANDBOX_BUYER_EMAIL")


def _overdue_invoices(
    session_factory: sessionmaker[Session],
) -> list[tuple[str, str, str | None]]:
    with session_factory() as session:
        return [
            (row.id, row.balance, row.paypal_invoice_id)
            for row in session.scalars(
                select(InvoiceRow)
                .where(InvoiceRow.status == InvoiceStatus.OVERDUE.value)
                .order_by(InvoiceRow.id)
            )
        ]


def _store_link(
    session_factory: sessionmaker[Session], invoice_id: str, paypal_invoice_id: str
) -> None:
    with session_factory.begin() as session:
        session.execute(
            update(InvoiceRow)
            .where(InvoiceRow.id == invoice_id)
            .values(paypal_invoice_id=paypal_invoice_id)
        )


def _open_original(
    session_factory: sessionmaker[Session],
    gateway: PayPalGateway,
    invoice_id: str,
    balance: str,
) -> None:
    """Create the draft, persist its id, then send it.

    A draft cannot be paid, so a crash after the draft is stored leaves nothing collectable
    twice: the next run finds the stored draft and sends it. No database transaction is open
    while PayPal is called.
    """
    ref = gateway.create_draft(
        NewInvoiceReq(invoice_number=f"{invoice_id}-{uuid4().hex[:8]}", amount=balance),
        request_id=f"sandbox-bootstrap-{invoice_id}",
    )
    _store_link(session_factory, invoice_id, ref.id)
    gateway.send_invoice(ref.id)


def prepare_sandbox(
    session_factory: sessionmaker[Session],
    gateway: PayPalGateway,
    *,
    relink_stale: bool = False,
) -> dict[str, list[str]]:
    """Open the original invoices that are missing and report what happened to each one."""
    report: dict[str, list[str]] = {"created": [], "sent": [], "kept": [], "stale": []}
    for invoice_id, balance, paypal_invoice_id in _overdue_invoices(session_factory):
        if paypal_invoice_id is None:
            _open_original(session_factory, gateway, invoice_id, balance)
            report["created"].append(invoice_id)
            continue
        status = gateway.get_invoice(paypal_invoice_id).status
        if status == DRAFT_STATUS:
            gateway.send_invoice(paypal_invoice_id)
            report["sent"].append(invoice_id)
        elif status in OPEN_STATUSES:
            report["kept"].append(invoice_id)
        elif relink_stale:
            _open_original(session_factory, gateway, invoice_id, balance)
            report["created"].append(invoice_id)
        else:
            report["stale"].append(invoice_id)
    return report


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Seed the database and open the original invoices in the PayPal Sandbox."
    )
    parser.add_argument(
        "--relink-stale",
        action="store_true",
        help="Open a new original invoice when the linked one is cancelled or already paid.",
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    require_sandbox(settings)
    Base.metadata.create_all(get_engine())
    session_factory = get_session_factory()
    with session_factory.begin() as session:
        seed_database(session)
    try:
        report = prepare_sandbox(
            session_factory, build_gateway(settings), relink_stale=args.relink_stale
        )
    except PayPalError as err:
        raise SystemExit(f"Sandbox bootstrap failed: {err.code}: {err.message}") from err
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
