from fastapi import APIRouter, Depends, status
from app.db_raw import get_raw_db
from app.schemas import UsageLogResponse, UsageSummary
from app.dependencies import get_current_tenant, get_current_user
from app.services.db.metering_db_service import MeteringDBService
from typing import List, Optional, Any
import uuid

router = APIRouter(prefix="/metering", tags=["metering"])

async def get_metering_service():
    return MeteringDBService()

@router.get("/summary", response_model=List[UsageSummary])
async def get_my_usage_summary(
    tenant: Any = Depends(get_current_tenant),
    current_user: Any = Depends(get_current_user),
    conn: Any = Depends(get_raw_db),
    service: MeteringDBService = Depends(get_metering_service)
):
    """
    Get a breakdown of current usage vs plan limits. 
    Superadmins see global totals. Tenant admins see organization-wide totals.
    """
    role_name = getattr(current_user.role, "name", "user") if hasattr(current_user, "role") else "user"
    return await service.get_usage_summary(conn, tenant.tenant_id, current_user.user_id, role_name)

@router.get("/logs", response_model=List[UsageLogResponse])
async def get_my_usage_logs(
    metric_name: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    tenant: Any = Depends(get_current_tenant),
    current_user: Any = Depends(get_current_user),
    conn: Any = Depends(get_raw_db),
    service: MeteringDBService = Depends(get_metering_service)
):
    """
    Get raw historical usage logs.
    """
    role_name = getattr(current_user.role, "name", "user") if hasattr(current_user, "role") else "user"
    is_admin = role_name in ["tenant_admin", "enterprise_tenant", "superadmin"]
    
    user_id_filter = None if is_admin else current_user.user_id
    return await service.list_metering_records(conn, tenant.tenant_id, limit, offset, metric_name, user_id_filter)

@router.post("/record", status_code=status.HTTP_201_CREATED)
async def record_custom_usage(
    metric_name: str,
    quantity: int = 1,
    current_user: Any = Depends(get_current_user),
    tenant: Any = Depends(get_current_tenant),
    conn: Any = Depends(get_raw_db),
    service: MeteringDBService = Depends(get_metering_service)
):
    """
    Manually record usage for a specific metric.
    """
    return await service.create_metering_record(conn, tenant.tenant_id, metric_name, quantity, current_user.user_id)
