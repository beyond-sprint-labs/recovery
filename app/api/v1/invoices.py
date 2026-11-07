"""Invoice read endpoints (F1-13, slice 1). Parse, delegate, serialize: nothing else."""

from fastapi import APIRouter

from app.core.deps import RecoveryServiceDep
from app.core.schemas import Invoice

router = APIRouter(tags=["invoices"])


@router.get("/invoices", response_model=list[Invoice])
def list_invoices(service: RecoveryServiceDep) -> list[Invoice]:
    return service.list_invoices()


@router.get("/invoices/{invoice_id}", response_model=Invoice)
def get_invoice(invoice_id: str, service: RecoveryServiceDep) -> Invoice:
    return service.get_invoice(invoice_id)
