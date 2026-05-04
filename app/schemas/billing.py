from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional, Dict, Any


class PlanBase(BaseModel):
    name: str
    description: Optional[str] = None
    price: float
    currency: str = "USD"
    limits: Dict[str, Any]
    is_active: Optional[bool] = True


class PlanCreate(PlanBase):
    stripe_monthly_price_id: Optional[str] = None
    stripe_yearly_price_id: Optional[str] = None
    paypal_plan_id: Optional[str] = None


class PlanUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    limits: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
    stripe_monthly_price_id: Optional[str] = None
    stripe_yearly_price_id: Optional[str] = None
    paypal_plan_id: Optional[str] = None


class PlanResponse(PlanBase):
    plan_id: UUID
    stripe_monthly_price_id: Optional[str] = None
    stripe_yearly_price_id: Optional[str] = None
    paypal_plan_id: Optional[str] = None

    class Config:
        from_attributes = True


class SubscriptionResponse(BaseModel):
    subscription_id: UUID
    status: str
    current_period_end: datetime
    plan: PlanResponse

    class Config:
        from_attributes = True


class UsageLogResponse(BaseModel):
    metric_name: str
    quantity: int
    created_on: datetime

    class Config:
        from_attributes = True


class InvoiceResponse(BaseModel):
    invoice_id: UUID
    amount: float
    currency: str
    status: str
    hosted_invoice_url: Optional[str] = None
    created_on: datetime

    class Config:
        from_attributes = True


class CheckoutSessionRequest(BaseModel):
    plan_id: UUID
    provider: str  # 'stripe' or 'paypal'
    interval: str = "month"  # 'month' or 'year'
    success_url: str
    cancel_url: str


class CheckoutSessionResponse(BaseModel):
    checkout_url: str
    session_id: Optional[str] = None  # Stripe Session ID or PayPal Order/Plan ID


class UsageSummary(BaseModel):
    metric_name: str
    total_quantity: float
    limit: Optional[int] = None
    usage_percent: Optional[float] = None
