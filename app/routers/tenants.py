"""
API router for tenant management using raw SQL.
"""
from typing import Any
from fastapi import APIRouter, Depends, HTTPException
import psycopg
import json

from app.db_raw import get_raw_db
from app.schemas import TenantResponse, TenantBase
from app.dependencies import get_current_tenant, get_tenant_service
from app.services.db.tenant_db_service import TenantDBService

router = APIRouter(prefix="/tenants", tags=["tenants"])

@router.post("/register", response_model=TenantResponse)
async def register_tenant(
    tenant: TenantBase, 
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    service: TenantDBService = Depends(get_tenant_service)
):
    """
    Register a new SaaS tenant on the platform using raw SQL.
    """
    db_tenant = await service.get_tenant_by_slug(conn, tenant.slug)
    if db_tenant:
        raise HTTPException(status_code=400, detail="Slug already taken")
    
    tenant_data = {
        "name": tenant.name,
        "type": tenant.type,
        "slug": tenant.slug,
        "org_name": tenant.org_name,
        "address": tenant.address
    }
    new_tenant = await service.create_tenant(conn, tenant_data)
    
    # Initialize default settings
    await service.initialize_tenant_settings(conn, new_tenant["tenant_id"])
    
    return new_tenant

@router.get("/dashboard")
async def get_tenant_dashboard(
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    tenant: Any = Depends(get_current_tenant),
    service: TenantDBService = Depends(get_tenant_service)
):
    """
    Retrieve comprehensive statistics for a tenant's dashboard using raw SQL.
    """
    metrics_data = await service.get_tenant_dashboard_metrics(conn, tenant.tenant_id)

    return {
        "tenant_id": tenant.tenant_id,
        "name": tenant.name,
        "org_name": tenant.org_name,
        "type": tenant.type,
        **metrics_data
    }


@router.get("/{tenant_id}/settings")
async def get_tenant_settings(
    tenant_id: str, 
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    service: TenantDBService = Depends(get_tenant_service)
):
    """
    Retrieve the configuration settings for a specific tenant using raw SQL.
    """
    config = await service.get_tenant_settings(conn, tenant_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Settings not found")
    return config

@router.put("/{tenant_id}/settings")
async def update_tenant_settings(
    tenant_id: str, 
    config: dict, 
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    service: TenantDBService = Depends(get_tenant_service)
):
    """
    Update the configuration settings for a specific tenant using raw SQL.
    """
    success = await service.update_tenant_settings(conn, tenant_id, config)
    if not success:
        raise HTTPException(status_code=404, detail="Settings not found")
    
    return {"status": "updated"}

