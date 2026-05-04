"""
API router for Role-Based Access Control (RBAC).
Provides endpoints for managing user roles and permissions within a tenant.
"""
from fastapi import APIRouter, Depends, HTTPException, status
import psycopg
import uuid
from typing import List, Optional, Any
from app.db_raw import get_raw_db
from app.schemas import (
    RoleCreate,
    RoleUpdate,
    RoleResponse
)
from app.dependencies import get_current_tenant, RoleChecker, get_role_service
from app.services.db.role_db_service import RoleDBService

router = APIRouter(prefix="/roles", tags=["roles"])

# Restrict custom role management to tenant admins
require_tenant_admin = RoleChecker(["enterprise_tenant", "superadmin"])

@router.get("", response_model=List[RoleResponse])
async def get_tenant_roles(
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    tenant: Any = Depends(get_current_tenant),
    service: RoleDBService = Depends(get_role_service),
    limit: int = 100,
    offset: int = 0,
    search: Optional[str] = None
):
    """
    Retrieve all roles applicable to the current tenant with pagination and search.
    Includes both system-wide roles (tenant_id IS NULL) and tenant-specific custom roles.
    """
    return await service.list_roles(conn, tenant.tenant_id, limit, offset, search)

@router.post("", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
async def create_custom_role(
    role_in: RoleCreate,
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    user: Any = Depends(require_tenant_admin),
    tenant: Any = Depends(get_current_tenant),
    service: RoleDBService = Depends(get_role_service)
):
    """
    Create a new custom role specific to the current tenant.
    Only accessible to tenant admins (e.g., enterprise_tenant).
    """
    # Check if role name already exists in this tenant or system
    existing = await service.get_role_by_name_and_tenant(conn, role_in.name, tenant.tenant_id)
    
    if existing:
        raise HTTPException(status_code=400, detail=f"Role name '{role_in.name}' already exists.")

    return await service.create_role(conn, tenant.tenant_id, role_in.name, role_in.permissions)

@router.patch("/{role_id}", response_model=RoleResponse)
async def update_custom_role(
    role_id: uuid.UUID,
    role_in: RoleUpdate,
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    user: Any = Depends(require_tenant_admin),
    tenant: Any = Depends(get_current_tenant),
    service: RoleDBService = Depends(get_role_service)
):
    """
    Update a custom role for the current tenant.
    System roles cannot be modified through this endpoint.
    """
    role = await service.get_tenant_role(conn, role_id, tenant.tenant_id)
    
    if not role:
        raise HTTPException(status_code=404, detail="Custom role not found or it is a system role.")

    update_data = role_in.model_dump(exclude_unset=True)
    if 'name' in update_data and update_data['name'] != role['name']:
        # Verify no conflict
        if await service.get_role_by_name_and_tenant(conn, update_data['name'], tenant.tenant_id):
            raise HTTPException(status_code=400, detail=f"Role name '{update_data['name']}' already exists.")

    return await service.update_role(conn, role_id, update_data)

@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_custom_role(
    role_id: uuid.UUID,
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    user: Any = Depends(require_tenant_admin),
    tenant: Any = Depends(get_current_tenant),
    service: RoleDBService = Depends(get_role_service)
):
    """
    Delete a custom role.
    """
    if not await service.get_tenant_role(conn, role_id, tenant.tenant_id):
        raise HTTPException(status_code=404, detail="Custom role not found or it is a system role.")

    # Check if users are assigned to this role
    if await service.is_role_assigned_to_users(conn, role_id):
        raise HTTPException(status_code=400, detail="Cannot delete role. Users are currently assigned to it.")

    await service.delete_role(conn, role_id)
    return None
