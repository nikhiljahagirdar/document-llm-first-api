from fastapi import APIRouter, Depends, HTTPException, status
import psycopg
from app.db_raw import get_raw_db
from app.schemas import PlanResponse, PlanCreate, PlanUpdate
from app.dependencies import get_superadmin
from app.services.db.plan_db_service import PlanDBService
from typing import List, Optional, Any
import uuid

router = APIRouter(prefix="/plans", tags=["plans"])

async def get_plan_service():
    return PlanDBService()

@router.get("", response_model=List[PlanResponse])
async def get_plans(
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    service: PlanDBService = Depends(get_plan_service)
):
    """
    List all available subscription plans.
    """
    return await service.list_plans(conn, active_only=True)

@router.post("", response_model=PlanResponse, status_code=status.HTTP_201_CREATED)
async def create_plan(
    plan: PlanCreate, 
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    service: PlanDBService = Depends(get_plan_service),
    admin: Any = Depends(get_superadmin)
):
    """
    Create a new subscription plan.
    """
    return await service.create_plan(conn, plan.model_dump())

@router.put("/{plan_id}", response_model=PlanResponse)
async def update_plan(
    plan_id: uuid.UUID, 
    plan_update: PlanUpdate, 
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    service: PlanDBService = Depends(get_plan_service),
    admin: Any = Depends(get_superadmin)
):
    """
    Update an existing subscription plan.
    """
    existing = await service.get_plan(conn, plan_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Plan not found")
    
    update_data = plan_update.model_dump(exclude_unset=True)
    return await service.update_plan(conn, plan_id, update_data)

@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plan(
    plan_id: uuid.UUID, 
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    service: PlanDBService = Depends(get_plan_service),
    admin: Any = Depends(get_superadmin)
):
    """
    Deactivate a subscription plan (sets is_active to FALSE).
    """
    existing = await service.get_plan(conn, plan_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Plan not found")
    
    # Actually deactivate instead of delete
    await service.update_plan(conn, plan_id, {"is_active": False})
    return None
