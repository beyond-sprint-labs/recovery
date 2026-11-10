import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.db import Base, get_engine, get_session_factory
from app.core.models import InvoiceRow
from app.paypal.gateway import PayPalError
from app.paypal.mock_gateway import MockPayPalGateway
from app.seed.loader import seed_database
from app.seed.sandbox_bootstrap import main, prepare_sandbox, require_sandbox

OVERDUE_IDS = ["INV-001", "INV-002", "INV-003"]
SANDBOX_URL = "https://api-m.sandbox.paypal.com"


@pytest.fixture
def seeded_factory() -> sessionmaker[Session]:
    Base.metadata.create_all(get_engine())
    factory = get_session_factory()
    with factory.begin() as session:
        seed_database(session)
    return factory


def _links(factory: sessionmaker[Session]) -> dict[str, str | None]:
    with factory() as session:
        return {row.id: row.paypal_invoice_id for row in session.scalars(select(InvoiceRow))}


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "paypal_mode": "real",
        "paypal_base_url": SANDBOX_URL,
        "paypal_sandbox_buyer_email": "buyer@example.com",
    }
    values.update(overrides)
    return Settings.model_validate(values)


def test_require_sandbox_accepts_a_sandbox_configuration() -> None:
    require_sandbox(_settings())


@pytest.mark.parametrize(
    "overrides",
    [
        {"paypal_mode": "mock"},
        {"paypal_base_url": "https://api-m.paypal.com"},
        {"paypal_sandbox_buyer_email": None},
    ],
)
def test_require_sandbox_refuses_unsafe_configurations(overrides: dict[str, object]) -> None:
    with pytest.raises(SystemExit):
        require_sandbox(_settings(**overrides))


def test_main_refuses_to_run_with_the_simulated_gateway() -> None:
    with pytest.raises(SystemExit):
        main([])


def test_prepare_sandbox_opens_one_original_per_overdue_invoice(
    seeded_factory: sessionmaker[Session],
) -> None:
    gateway = MockPayPalGateway()
    report = prepare_sandbox(seeded_factory, gateway)
    assert report == {"created": OVERDUE_IDS, "sent": [], "kept": [], "stale": []}
    links = _links(seeded_factory)
    assert links["INV-004"] is None
    assert links["INV-005"] is None
    for invoice_id in OVERDUE_IDS:
        paypal_invoice_id = links[invoice_id]
        assert paypal_invoice_id is not None
        assert gateway.invoices_db[paypal_invoice_id]["status"] == "SENT"


def test_prepare_sandbox_is_idempotent(seeded_factory: sessionmaker[Session]) -> None:
    gateway = MockPayPalGateway()
    prepare_sandbox(seeded_factory, gateway)
    before = _links(seeded_factory)
    report = prepare_sandbox(seeded_factory, gateway)
    assert report == {"created": [], "sent": [], "kept": OVERDUE_IDS, "stale": []}
    assert _links(seeded_factory) == before
    assert len(gateway.invoices_db) == len(OVERDUE_IDS)


def test_prepare_sandbox_resumes_a_stored_draft_without_creating_another(
    seeded_factory: sessionmaker[Session],
) -> None:
    gateway = MockPayPalGateway()
    gateway.fail_steps = {"send"}
    with pytest.raises(PayPalError):
        prepare_sandbox(seeded_factory, gateway)
    stored = _links(seeded_factory)["INV-001"]
    assert stored is not None
    assert gateway.invoices_db[stored]["status"] == "DRAFT"

    report = prepare_sandbox(seeded_factory, gateway)
    assert report == {
        "created": ["INV-002", "INV-003"],
        "sent": ["INV-001"],
        "kept": [],
        "stale": [],
    }
    assert _links(seeded_factory)["INV-001"] == stored
    assert gateway.invoices_db[stored]["status"] == "SENT"
    assert len(gateway.invoices_db) == len(OVERDUE_IDS)


def test_prepare_sandbox_reports_and_relinks_stale_originals(
    seeded_factory: sessionmaker[Session],
) -> None:
    gateway = MockPayPalGateway()
    prepare_sandbox(seeded_factory, gateway)
    original = _links(seeded_factory)["INV-001"]
    assert original is not None
    gateway.cancel_invoice(original)

    reported = prepare_sandbox(seeded_factory, gateway)
    assert reported == {
        "created": [],
        "sent": [],
        "kept": ["INV-002", "INV-003"],
        "stale": ["INV-001"],
    }
    assert _links(seeded_factory)["INV-001"] == original

    relinked = prepare_sandbox(seeded_factory, gateway, relink_stale=True)
    assert relinked == {
        "created": ["INV-001"],
        "sent": [],
        "kept": ["INV-002", "INV-003"],
        "stale": [],
    }
    replacement = _links(seeded_factory)["INV-001"]
    assert replacement is not None
    assert replacement != original
    assert gateway.invoices_db[replacement]["status"] == "SENT"
