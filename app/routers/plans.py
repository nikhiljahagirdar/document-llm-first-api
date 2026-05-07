from fastapi import APIRouter, Depends, HTTPException, status
import psycopg
from app.db_raw import get_raw_db
from app.schemas import PlanResponse, PlanCreate, PlanUpdate
from app.dependencies import get_superadmin
from app.services.db.plan_db_service import PlanDBService
from typing import List, Optional, Any
import uuid
import stripe
import os

router = APIRouter(prefix="/plans", tags=["plans"])

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

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
    plan_data = plan.model_dump()

    # Stripe synchronization for paid plans
    if plan_data.get('price', 0) > 0 and stripe.api_key:
        try:
            # 1. Look for existing product in Stripe by name
            all_products = stripe.Product.list(limit=100, active=True)
            product = next((p for p in all_products if p.name == plan_data['name']), None)

            if not product:
                product = stripe.Product.create(
                    name=plan_data['name'],
                    description=plan_data.get('description')
                )
            
            # 2. Sync Prices (Check if matching amounts already exist)
            existing_prices = stripe.Price.list(product=product.id, active=True)
            
            monthly_amount = int(plan_data['price'] * 100)
            yearly_amount = int(round(plan_data['price'] * 10, 2) * 100)

            stripe_monthly_id = next((p.id for p in existing_prices if p.recurring and p.recurring['interval'] == 'month' and p.unit_amount == monthly_amount), None)
            stripe_yearly_id = next((p.id for p in existing_prices if p.recurring and p.recurring['interval'] == 'year' and p.unit_amount == yearly_amount), None)

            if not stripe_monthly_id:
                monthly_price = stripe.Price.create(
                    product=product.id,
                    unit_amount=monthly_amount,
                    currency=plan_data.get('currency', 'usd').lower(),
                    recurring={"interval": "month"}
                )
                stripe_monthly_id = monthly_price.id
            
            if not stripe_yearly_id:
                yearly_price = stripe.Price.create(
                    product=product.id,
                    unit_amount=yearly_amount,
                    currency=plan_data.get('currency', 'usd').lower(),
                    recurring={"interval": "year"}
                )
                stripe_yearly_id = yearly_price.id

            plan_data['stripe_monthly_price_id'] = stripe_monthly_id
            plan_data['stripe_yearly_price_id'] = stripe_yearly_id

        except stripe.error.StripeError as e:
            # Log the error and proceed or raise depending on preference
            raise HTTPException(status_code=500, detail=f"Stripe synchronization failed: {str(e)}")

    return await service.create_plan(conn, plan_data)

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
