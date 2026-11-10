from collections.abc import Iterator

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.core.db import Base, get_engine, get_session_factory
from app.core.demo_bootstrap import bootstrap_demo, demo_bootstrap_enabled, link_open_invoices
from app.core.deps import get_paypal_gateway
from app.core.models import InvoiceRow
from app.paypal.mock_gateway import MockPayPalGateway
from app.seed.loader import seed_database

OPEN_STATUSES = {"SENT", "UNPAID"}
OVERDUE_BALANCES = {"INV-001": "1000.00", "INV-002": "250.50", "INV-003": "1500.00"}


@pytest.fixture(autouse=True)
def fresh_gateway() -> Iterator[None]:
    get_paypal_gateway.cache_clear()
    yield
    get_paypal_gateway.cache_clear()


@pytest.fixture
def tables() -> sessionmaker[Session]:
    Base.metadata.create_all(get_engine())
    return get_session_factory()


@pytest.fixture
def seeded_factory(tables: sessionmaker[Session]) -> sessionmaker[Session]:
    with tables.begin() as session:
        seed_database(session)
    return tables


def _stored_links(factory: sessionmaker[Session]) -> dict[str, str | None]:
    with factory() as session:
        return {row.id: row.paypal_invoice_id for row in session.scalars(select(InvoiceRow))}


@pytest.mark.parametrize(
    ("app_env", "demo_mode", "paypal_mode", "expected"),
    [
        ("local", True, "mock", True),
        ("test", True, "mock", False),
        ("local", False, "mock", False),
        ("local", True, "real", False),
    ],
)
def test_bootstrap_is_enabled_only_for_the_local_demo_preset(
    app_env: str, demo_mode: bool, paypal_mode: str, expected: bool
) -> None:
    settings = Settings.model_validate(
        {"app_env": app_env, "demo_mode": demo_mode, "paypal_mode": paypal_mode}
    )
    assert demo_bootstrap_enabled(settings) is expected


def test_link_open_invoices_links_only_overdue_invoices(
    seeded_factory: sessionmaker[Session],
) -> None:
    gateway = MockPayPalGateway()
    links = link_open_invoices(seeded_factory, gateway)
    assert set(links) == set(OVERDUE_BALANCES)
    stored = _stored_links(seeded_factory)
    assert {key: value for key, value in stored.items() if value is not None} == links
    assert stored["INV-004"] is None
    assert stored["INV-005"] is None
    created = {item["id"]: item for item in gateway.invoices_db.values()}
    for invoice_id, paypal_invoice_id in links.items():
        assert created[paypal_invoice_id]["status"] in OPEN_STATUSES
        assert created[paypal_invoice_id]["req"].amount == OVERDUE_BALANCES[invoice_id]


def test_link_open_invoices_can_run_again_on_the_same_gateway(
    seeded_factory: sessionmaker[Session],
) -> None:
    gateway = MockPayPalGateway()
    first = link_open_invoices(seeded_factory, gateway)
    second = link_open_invoices(seeded_factory, gateway)
    assert set(second) == set(first)
    assert all(second[invoice_id] != first[invoice_id] for invoice_id in first)
    stored = _stored_links(seeded_factory)
    assert {key: value for key, value in stored.items() if value is not None} == second


def test_bootstrap_does_nothing_outside_the_local_demo(tables: sessionmaker[Session]) -> None:
    bootstrap_demo(get_settings())
    with tables() as session:
        assert session.scalar(select(func.count()).select_from(InvoiceRow)) == 0


def test_bootstrap_seeds_and_links_in_the_local_demo(tables: sessionmaker[Session]) -> None:
    settings = Settings.model_validate(
        {"app_env": "local", "demo_mode": True, "paypal_mode": "mock"}
    )
    bootstrap_demo(settings)
    gateway = get_paypal_gateway()
    assert isinstance(gateway, MockPayPalGateway)
    known = {item["id"] for item in gateway.invoices_db.values()}
    with tables() as session:
        assert session.scalar(select(func.count()).select_from(InvoiceRow)) == 5
        invoice = session.get(InvoiceRow, "INV-001")
        assert invoice is not None
        assert invoice.paypal_invoice_id in known
