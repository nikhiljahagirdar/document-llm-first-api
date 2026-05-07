from fastapi import APIRouter, Depends, HTTPException, status
import psycopg
from app.db_raw import get_raw_db
from app.schemas import (
    SubscriptionResponse, 
    CheckoutSessionResponse, 
    CheckoutSessionRequest, 
    InvoiceResponse
) 
from app.dependencies import get_current_tenant, get_current_user, get_optional_tenant, get_optional_user, RoleChecker
from typing import List, Optional, Any 
from pydantic import BaseModel
import os
import stripe
import httpx
import uuid
from datetime import datetime
from dotenv import load_dotenv
from app.services.db.billing_db_service import BillingDBService
from app.services.db.audit_log_db_service import AuditLogDBService

load_dotenv()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID")
PAYPAL_CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET")
PAYPAL_MODE = os.getenv("PAYPAL_MODE", "sandbox")
PAYPAL_API_BASE = "https://api-m.sandbox.paypal.com" if PAYPAL_MODE == "sandbox" else "https://api-m.paypal.com"

router = APIRouter(prefix="/billing", tags=["billing"])

async def get_billing_service():
    return BillingDBService()

async def get_paypal_access_token():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{PAYPAL_API_BASE}/v1/oauth2/token",
            auth=(PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET),
            data={"grant_type": "client_credentials"},
        )
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail="Failed to authenticate with PayPal")
        return response.json()["access_token"]

@router.get("/subscription", response_model=SubscriptionResponse)
async def get_tenant_subscription(
    tenant: Any = Depends(get_current_tenant), 
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    service: BillingDBService = Depends(get_billing_service)
):
    sub = await service.get_tenant_subscription(conn, tenant.tenant_id)
    if not sub:
        plan_id = await service.get_any_plan_id(conn)
        if not plan_id:
             raise HTTPException(status_code=404, detail="No subscription plans configured")
        await service.create_trial_subscription(conn, tenant.tenant_id, plan_id)
        sub = await service.get_tenant_subscription(conn, tenant.tenant_id)
    return sub

@router.post("/checkout", response_model=CheckoutSessionResponse)
async def create_checkout_session(
    request: CheckoutSessionRequest,
    current_user: Optional[Any] = Depends(get_optional_user),
    tenant: Optional[Any] = Depends(get_optional_tenant),
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    service: BillingDBService = Depends(get_billing_service)
):
    plan = await service.get_plan_by_id(conn, request.plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    # Record Audit Log for checkout start if user is logged in
    if current_user and tenant:
        await AuditLogDBService.record_audit_log(
            conn, tenant.tenant_id, current_user.user_id, 
            "checkout_initiated", "billing", str(plan["plan_id"]), 
            {"provider": request.provider, "plan_name": plan["name"]}
        )

    customer_email = current_user.email if current_user else None
    client_reference_id = str(tenant.tenant_id) if tenant else None
    metadata = {"plan_id": str(plan["plan_id"])}
    if tenant:
        metadata["tenant_id"] = str(tenant.tenant_id)

    if request.provider == "stripe":
        stripe_price_id = plan["stripe_monthly_price_id"] if request.interval == "month" else plan["stripe_yearly_price_id"]
        if not stripe_price_id:
            raise HTTPException(status_code=400, detail=f"Stripe {request.interval} pricing not configured")
        
        try:
            checkout_session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=[{'price': stripe_price_id, 'quantity': 1}],
                mode='subscription',
                success_url=request.success_url + "?session_id={CHECKOUT_SESSION_ID}",
                cancel_url=request.cancel_url,
                client_reference_id=client_reference_id,
                customer_email=customer_email,
                metadata=metadata
            )
            return {"checkout_url": checkout_session.url, "session_id": checkout_session.id}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    elif request.provider == "paypal":
        if not plan["paypal_plan_id"]:
             raise HTTPException(status_code=400, detail="PayPal not configured")
        
        access_token = await get_paypal_access_token()
        async with httpx.AsyncClient() as client:
            json_payload = {
                "plan_id": plan["paypal_plan_id"],
                "application_context": {
                    "brand_name": "Document Intelligence Platform",
                    "return_url": request.success_url,
                    "cancel_url": request.cancel_url,
                    "user_action": "SUBSCRIBE_NOW"
                }
            }
            if customer_email:
                json_payload["subscriber"] = {"email_address": customer_email}
            if client_reference_id:
                json_payload["custom_id"] = client_reference_id

            response = await client.post(
                f"{PAYPAL_API_BASE}/v1/billing/subscriptions",
                headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                json=json_payload
            )
            if response.status_code != 201:
                raise HTTPException(status_code=500, detail=f"PayPal error: {response.text}")
            
            data = response.json()
            checkout_url = next(link["href"] for link in data["links"] if link["rel"] == "approve")
            return {"checkout_url": checkout_url, "session_id": data["id"]}

    raise HTTPException(status_code=400, detail="Invalid provider")

@router.get("/history", response_model=List[InvoiceResponse])
@router.get("/invoices", response_model=List[InvoiceResponse])
async def get_billing_history(
    search: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    tenant: Any = Depends(get_current_tenant), 
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    service: BillingDBService = Depends(get_billing_service)
):
    """
    Retrieve payment and invoice history for the current tenant.
    """
    return await service.list_billing_records(conn, tenant.tenant_id, limit, offset, search)

@router.post("/webhooks/stripe")
async def stripe_webhook(
    payload: dict,
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    service: BillingDBService = Depends(get_billing_service)
):
    event_type = payload.get("type")
    data_object = payload.get("data", {}).get("object", {})

    if event_type == "invoice.paid":
        tenant_id = data_object.get("metadata", {}).get("tenant_id")
        if tenant_id:
            await service.create_billing_record(
                conn, 
                uuid.UUID(tenant_id),
                amount=data_object.get("amount_paid") / 100,
                currency=data_object.get("currency"),
                status="paid",
                stripe_invoice_id=data_object.get("id"),
                paid_at=datetime.now()
            )
            await AuditLogDBService.record_audit_log(
                conn, uuid.UUID(tenant_id), uuid.UUID(int=0),
                "payment_received", "billing", data_object.get("id"),
                {"provider": "stripe", "amount": data_object.get("amount_paid") / 100}
            )

    return {"status": "received"}


class StripeSyncResponse(BaseModel):
    synced_plans: int
    created_products: int
    created_prices: int
    details: List[str]

require_superadmin = RoleChecker(["Super Admin"])

@router.post(
    "/plans/sync-stripe", 
    response_model=StripeSyncResponse,
    summary="Synchronize database plans with Stripe",
    description="Reads all subscription plans from the database, creates corresponding Products and Prices in Stripe if they don't exist, and updates the database with the Stripe Price IDs. This is an idempotent operation.",
    dependencies=[Depends(require_superadmin)]
)
async def sync_plans_with_stripe(
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    service: BillingDBService = Depends(get_billing_service)
):
    if not stripe.api_key:
        raise HTTPException(status_code=503, detail="Stripe is not configured on the server.")

    logs = []
    created_products_count = 0
    created_prices_count = 0
    
    try:
        db_plans = await service.get_all_plans(conn)
        if not db_plans:
            return {"synced_plans": 0, "created_products": 0, "created_prices": 0, "details": ["No plans found in the database to sync."]}

        logs.append("Fetching existing products from Stripe...")
        all_products = stripe.Product.list(limit=100, active=True)
        existing_stripe_products = {prod.name: prod for prod in all_products}
        logs.append(f"Found {len(existing_stripe_products)} existing products in Stripe.")

        for plan in db_plans:
            if not plan.get('price') or plan['price'] <= 0:
                logs.append(f"Skipping plan '{plan['name']}' (free plan).")
                continue

            logs.append(f"Processing plan '{plan['name']}'...")
            product = None
            
            if plan['name'] in existing_stripe_products:
                product = existing_stripe_products[plan['name']]
                logs.append(f"  - Product '{plan['name']}' already exists in Stripe (ID: {product.id}).")
            else:
                product = stripe.Product.create(
                    name=plan['name'],
                    description=plan.get('description'),
                    metadata={'plan_id': str(plan['plan_id'])}
                )
                created_products_count += 1
                logs.append(f"  - Created new product in Stripe (ID: {product.id}).")
            
            existing_prices = stripe.Price.list(product=product.id, active=True)
            
            # Look for existing prices matching the amount to avoid duplicate price objects
            monthly_amount = int(plan['price'] * 100)
            yearly_amount = int(round(plan['price'] * 10, 2) * 100) # 12 months for price of 10
            
            stripe_monthly_id = next((p.id for p in existing_prices if p.recurring and p.recurring['interval'] == 'month' and p.unit_amount == monthly_amount), None)
            stripe_yearly_id = next((p.id for p in existing_prices if p.recurring and p.recurring['interval'] == 'year' and p.unit_amount == yearly_amount), None)

            if not stripe_monthly_id:
                monthly_price_obj = stripe.Price.create(product=product.id, unit_amount=monthly_amount, currency=plan.get('currency', 'usd').lower(), recurring={"interval": "month"})
                stripe_monthly_id = monthly_price_obj.id
                created_prices_count += 1
                logs.append(f"  - Created monthly price: {stripe_monthly_id}")

            if not stripe_yearly_id:
                yearly_price_obj = stripe.Price.create(product=product.id, unit_amount=yearly_amount, currency=plan.get('currency', 'usd').lower(), recurring={"interval": "year"})
                stripe_yearly_id = yearly_price_obj.id
                created_prices_count += 1
                logs.append(f"  - Created yearly price (10x monthly): {stripe_yearly_id}")

            if (stripe_monthly_id != plan.get('stripe_monthly_price_id') or stripe_yearly_id != plan.get('stripe_yearly_price_id')):
                await service.update_plan_stripe_ids(conn, plan['plan_id'], stripe_monthly_id, stripe_yearly_id)
                logs.append(f"  - Updated database for plan '{plan['name']}'.")

        return {"synced_plans": len([p for p in db_plans if p.get('price', 0) > 0]), "created_products": created_products_count, "created_prices": created_prices_count, "details": logs}

    except stripe.error.StripeError as e:
        raise HTTPException(status_code=500, detail=f"A Stripe API error occurred: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")

@router.post("/webhooks/paypal")
async def paypal_webhook(
    payload: dict,
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    service: BillingDBService = Depends(get_billing_service)
):
    event_type = payload.get("event_type")
    resource = payload.get("resource", {})

    if event_type == "PAYMENT.SALE.COMPLETED":
        tenant_id = payload.get("custom_id")
        if tenant_id:
            await service.create_billing_record(
                conn,
                uuid.UUID(tenant_id),
                amount=float(resource.get("amount", {}).get("total", 0)),
                currency=resource.get("amount", {}).get("currency"),
                status="paid",
                paypal_invoice_id=resource.get("id"),
                paid_at=datetime.now()
            )
            await AuditLogDBService.record_audit_log(
                conn, uuid.UUID(tenant_id), uuid.UUID(int=0),
                "payment_received", "billing", resource.get("id"),
                {"provider": "paypal", "amount": resource.get("amount", {}).get("total")}
            )

    return {"status": "received"}


class StripeSyncRequest(BaseModel):
    session_id: str

@router.post(
    "/sync-session",
    summary="Synchronize checkout session and update subscription/invoice directly via Stripe SDK",
    description="Fetches checkout session details directly using Stripe SDK and updates tenant subscription and invoice records."
)
async def sync_checkout_session(
    request: StripeSyncRequest,
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    service: BillingDBService = Depends(get_billing_service)
):
    from datetime import timedelta
    if not stripe.api_key:
        raise HTTPException(status_code=503, detail="Stripe is not configured.")
    try:
        session = stripe.checkout.Session.retrieve(request.session_id, expand=["subscription"])
        
        tenant_id_str = session.metadata.get("tenant_id") or session.client_reference_id
        plan_id_str = session.metadata.get("plan_id")
        
        if not tenant_id_str or not plan_id_str:
            raise HTTPException(status_code=400, detail="Required metadata not found in Stripe session.")
            
        tenant_id = uuid.UUID(tenant_id_str)
        plan_id = uuid.UUID(plan_id_str)
        
        subscription_obj = session.subscription
        stripe_sub_id = None
        status = "active"
        period_start = datetime.now()
        period_end = datetime.now() + timedelta(days=30)
        cancel_at_period_end = False
        
        if subscription_obj:
            if isinstance(subscription_obj, str):
                stripe_sub_id = subscription_obj
                sub_detail = stripe.Subscription.retrieve(stripe_sub_id)
                status = sub_detail.status
                period_start = datetime.fromtimestamp(sub_detail.current_period_start)
                period_end = datetime.fromtimestamp(sub_detail.current_period_end)
                cancel_at_period_end = sub_detail.cancel_at_period_end
            else:
                stripe_sub_id = subscription_obj.id
                status = subscription_obj.status
                period_start = datetime.fromtimestamp(subscription_obj.current_period_start)
                period_end = datetime.fromtimestamp(subscription_obj.current_period_end)
                cancel_at_period_end = subscription_obj.cancel_at_period_end
        
        # Upsert subscription
        new_sub = await service.upsert_subscription(
            conn,
            tenant_id=tenant_id,
            plan_id=plan_id,
            status=status,
            stripe_subscription_id=stripe_sub_id,
            current_period_start=period_start,
            current_period_end=period_end,
            cancel_at_period_end=cancel_at_period_end
        )
        
        # Check if invoice record exists, if not, create it
        amount = (session.amount_total or 0) / 100.0
        currency = session.currency or "usd"
        
        invoice_record = None
        if session.invoice:
            existing_invoices = await service.list_billing_records(conn, tenant_id, limit=10)
            invoice_exists = any(inv.get("stripe_invoice_id") == session.invoice for inv in existing_invoices)
            if not invoice_exists:
                invoice_record = await service.create_billing_record(
                    conn,
                    tenant_id=tenant_id,
                    amount=amount,
                    currency=currency,
                    status="paid",
                    stripe_invoice_id=session.invoice,
                    paid_at=datetime.now()
                )
                await AuditLogDBService.record_audit_log(
                    conn, tenant_id, uuid.UUID(int=0),
                    "payment_received", "billing", session.invoice,
                    {"provider": "stripe", "amount": amount, "method": "stripe_sdk_sync"}
                )
                
        sub_serialized = {k: str(v) if isinstance(v, uuid.UUID) else v for k, v in new_sub.items()}
        if isinstance(sub_serialized.get("current_period_start"), datetime):
            sub_serialized["current_period_start"] = sub_serialized["current_period_start"].isoformat()
        if isinstance(sub_serialized.get("current_period_end"), datetime):
            sub_serialized["current_period_end"] = sub_serialized["current_period_end"].isoformat()
        if isinstance(sub_serialized.get("created_on"), datetime):
            sub_serialized["created_on"] = sub_serialized["created_on"].isoformat()
        if isinstance(sub_serialized.get("updated_on"), datetime):
            sub_serialized["updated_on"] = sub_serialized["updated_on"].isoformat()
            
        return {
            "status": "success",
            "subscription": sub_serialized,
            "invoice_created": invoice_record is not None
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=500, detail=f"Stripe error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")

