from fastapi import APIRouter, Depends, HTTPException, status
import psycopg
from app.db_raw import get_raw_db
from app.schemas import (
    SubscriptionResponse, 
    CheckoutSessionResponse, 
    CheckoutSessionRequest, 
    InvoiceResponse
)
from app.dependencies import get_current_tenant, get_current_user, get_optional_tenant, get_optional_user
from typing import List, Optional, Any
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
