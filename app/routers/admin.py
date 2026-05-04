from fastapi import APIRouter, Depends, HTTPException, status
import psycopg
from app.db_raw import get_raw_db
from app.schemas import InvoiceResponse, TenantResponse
from app.dependencies import get_superadmin
from typing import List, Optional, Any
from app.services.db.admin_db_service import AdminDBService

router = APIRouter(
    prefix="/admin", 
    tags=["admin"],
    dependencies=[Depends(get_superadmin)]
)

async def get_admin_service():
    return AdminDBService()

@router.get("/metrics")
async def get_platform_metrics(
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    service: AdminDBService = Depends(get_admin_service)
):
    """
    Retrieve comprehensive platform metrics using raw SQL.
    """
    return await service.get_platform_metrics(conn)

@router.get("/billing/failed", response_model=List[InvoiceResponse])
async def get_failed_payments(
    limit: int = 50,
    offset: int = 0,
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    service: AdminDBService = Depends(get_admin_service)
):
    return await service.get_failed_payments(conn, limit, offset)

@router.get("/tenants", response_model=List[TenantResponse])
async def list_all_tenants(
    search: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    service: AdminDBService = Depends(get_admin_service)
):
    return await service.list_all_tenants(conn, search, limit, offset)

@router.post("/tenants/{tenant_id}/suspend")
async def suspend_tenant(
    tenant_id: str, 
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    service: AdminDBService = Depends(get_admin_service)
):
    success = await service.suspend_tenant(conn, tenant_id)
    if not success:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return {"status": "suspended"}
