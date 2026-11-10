"""Local demo bootstrap: seed the database and link overdue invoices to the simulated PayPal."""

from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.db import get_session_factory
from app.core.deps import get_paypal_gateway
from app.core.models import InvoiceRow
from app.core.schemas import InvoiceStatus
from app.paypal.gateway import NewInvoiceReq, PayPalGateway
from app.seed.loader import seed_database

DEMO_ENVIRONMENT = "local"


def demo_bootstrap_enabled(settings: Settings) -> bool:
    """Run only for a local execution of the demo preset with the simulated gateway."""
    return (
        settings.demo_mode
        and settings.paypal_mode == "mock"
        and settings.app_env == DEMO_ENVIRONMENT
    )


def link_open_invoices(
    session_factory: sessionmaker[Session], gateway: PayPalGateway
) -> dict[str, str]:
    """Create and send one original PayPal invoice per overdue invoice and store its id.

    The gateway is called with no database transaction open: overdue invoices are read first,
    the PayPal calls run next, and the resulting ids are written in a separate short transaction.
    """
    with session_factory() as session:
        overdue = [
            (row.id, row.balance)
            for row in session.scalars(
                select(InvoiceRow)
                .where(InvoiceRow.status == InvoiceStatus.OVERDUE.value)
                .order_by(InvoiceRow.id)
            )
        ]
    links: dict[str, str] = {}
    for invoice_id, balance in overdue:
        suffix = uuid4().hex[:8]
        ref = gateway.create_draft(
            NewInvoiceReq(invoice_number=f"{invoice_id}-{suffix}", amount=balance),
            request_id=f"demo-{invoice_id}-{suffix}",
        )
        gateway.send_invoice(ref.id)
        links[invoice_id] = ref.id
    with session_factory.begin() as session:
        for invoice_id, paypal_invoice_id in links.items():
            session.execute(
                update(InvoiceRow)
                .where(InvoiceRow.id == invoice_id)
                .values(paypal_invoice_id=paypal_invoice_id)
            )
    return links


def bootstrap_demo(settings: Settings) -> None:
    """Seed the demo data and open the original invoices in the simulated gateway."""
    if not demo_bootstrap_enabled(settings):
        return
    session_factory = get_session_factory()
    with session_factory.begin() as session:
        seed_database(session)
    link_open_invoices(session_factory, get_paypal_gateway())
