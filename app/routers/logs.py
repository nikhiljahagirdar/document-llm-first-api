from fastapi import APIRouter, Depends, HTTPException
from app.schemas import UsageLogResponse, UsageSummary, AuditLogResponse
from app.dependencies import get_current_tenant, get_current_user
from typing import List, Optional, Any
import psycopg
from app.db_raw import get_raw_db
from app.services.db.metering_db_service import MeteringDBService
from app.services.db.audit_log_db_service import AuditLogDBService
import uuid

router = APIRouter(prefix="/logs", tags=["logs"])

async def get_metering_service():
    return MeteringDBService()

async def get_audit_log_service():
    return AuditLogDBService()

@router.get("/usage", response_model=List[UsageLogResponse])
async def get_my_usage_logs(
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    tenant: Any = Depends(get_current_tenant), 
    current_user: Any = Depends(get_current_user),
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    service: MeteringDBService = Depends(get_metering_service)
):
    """
    Retrieve metered usage logs with search and pagination.
    Admins see entire tenant usage. Users see their own.
    """
    role_name = getattr(current_user.role, "name", "user") if hasattr(current_user, "role") else "user"
    role_key = role_name.lower().replace(" ", "_")
    is_admin = role_key in ["tenant_admin", "enterprise_tenant", "super_admin", "superadmin"]
    
    user_id_filter = None if is_admin else current_user.user_id
    return await service.list_metering_records(conn, tenant.tenant_id, limit, offset, search, user_id_filter)

@router.get("/usage/summary", response_model=List[UsageSummary])
async def get_usage_summary(
    tenant: Any = Depends(get_current_tenant), 
    current_user: Any = Depends(get_current_user),
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    service: MeteringDBService = Depends(get_metering_service)
):
    """
    Retrieve an aggregated summary of usage for the current billing period.
    Superadmins see global totals. Tenant admins see organization totals.
    """
    role_name = getattr(current_user.role, "name", "user") if hasattr(current_user, "role") else "user"
    return await service.get_usage_summary(conn, tenant.tenant_id, current_user.user_id, role_name)

@router.post("/usage")
async def log_usage(
    metric: str, 
    quantity: int, 
    tenant: Any = Depends(get_current_tenant), 
    current_user: Any = Depends(get_current_user),
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    service: MeteringDBService = Depends(get_metering_service)
):
    """
    Log a new metered usage event.
    """
    await service.create_metering_record(conn, tenant.tenant_id, metric, quantity, current_user.user_id)
    return {"status": "success"}

@router.get("/audit", response_model=List[AuditLogResponse])
async def get_my_audit_logs(
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    tenant: Any = Depends(get_current_tenant), 
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    service: AuditLogDBService = Depends(get_audit_log_service)
):
    """
    Retrieve security and activity audit logs for the current tenant with search and pagination.
    """
    return await service.list_logs(conn, tenant.tenant_id, limit, offset, search)

@router.post("/audit")
async def create_audit_log(
    action: str, 
    resource_type: str, 
    resource_id: str = None, 
    details: dict = None,
    tenant: Any = Depends(get_current_tenant), 
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    service: AuditLogDBService = Depends(get_audit_log_service)
):
    """
    Manually create a new audit log entry.
    """
    await service.create_log(conn, tenant.tenant_id, action, resource_type, resource_id, details)
    return {"status": "logged"}
