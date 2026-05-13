import asyncpg
from typing import List, Optional
import uuid
from datetime import datetime
import json
from app.services.db.base_db_service import BaseDBService

class BillingDBService(BaseDBService):
    async def get_tenant_subscription(self, conn: asyncpg.Connection, tenant_id: uuid.UUID) -> Optional[dict]:
        query = """
            SELECT 
                s.subscription_id, s.tenant_id, s.plan_id, s.status, 
                s.stripe_subscription_id, s.current_period_start, s.current_period_end,
                p.name as plan_name, p.description as plan_description, p.price as plan_price, 
                p.currency as plan_currency, p.limits as plan_limits,
                p.stripe_monthly_price_id, p.stripe_yearly_price_id, p.paypal_plan_id
            FROM subscriptions s
            LEFT JOIN subscription_plans p ON s.plan_id = p.plan_id
            WHERE s.tenant_id = %s::uuid
            LIMIT 1
        """
        res = await self.fetch_one(conn, query, (tenant_id,))
        if not res:
            return None
            
        # Structure the plan dictionary
        plan_limits = res.get("plan_limits")
        if isinstance(plan_limits, str):
            try:
                plan_limits = json.loads(plan_limits)
            except Exception:
                plan_limits = {}

        plan = {
            "plan_id": res["plan_id"],
            "name": res["plan_name"],
            "description": res["plan_description"],
            "price": res["plan_price"],
            "currency": res["plan_currency"],
            "limits": plan_limits,
            "stripe_monthly_price_id": res.get("stripe_monthly_price_id"),
            "stripe_yearly_price_id": res.get("stripe_yearly_price_id"),
            "paypal_plan_id": res.get("paypal_plan_id")
        }
        
        return {
            "subscription_id": res["subscription_id"],
            "tenant_id": res["tenant_id"],
            "plan_id": res["plan_id"],
            "status": res["status"],
            "stripe_subscription_id": res.get("stripe_subscription_id"),
            "current_period_start": res.get("current_period_start"),
            "current_period_end": res.get("current_period_end"),
            "plan": plan
        }

    async def get_any_plan_id(self, conn: asyncpg.Connection) -> Optional[uuid.UUID]:
        query = "SELECT plan_id FROM subscription_plans LIMIT 1"
        result = await self.fetch_one(conn, query)
        return result["plan_id"] if result else None

    async def create_trial_subscription(self, conn: asyncpg.Connection, tenant_id: uuid.UUID, plan_id: uuid.UUID) -> None:
        query = "INSERT INTO subscriptions (tenant_id, plan_id, status) VALUES (%s::uuid, %s::uuid, 'trial')"
        await self.execute(conn, query, (tenant_id, plan_id))

    async def get_plan_by_id(self, conn: asyncpg.Connection, plan_id: uuid.UUID) -> Optional[dict]:
        query = "SELECT * FROM subscription_plans WHERE plan_id = %s::uuid"
        res = await self.fetch_one(conn, query, (plan_id,))
        if res and isinstance(res.get("limits"), str):
            try: res["limits"] = json.loads(res["limits"])
            except: res["limits"] = {}
        return res

    async def list_billing_records(self, conn: asyncpg.Connection, tenant_id: uuid.UUID, limit: int = 100, offset: int = 0, search: Optional[str] = None) -> List[dict]:
        query = "SELECT * FROM invoices WHERE tenant_id = %s::uuid"
        params = [tenant_id]
        if search:
            query += " AND (stripe_invoice_id ILIKE %s OR paypal_invoice_id ILIKE %s OR status ILIKE %s OR CAST(amount AS TEXT) ILIKE %s)"
            params.extend([f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%"])
        query += " ORDER BY created_on DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        return await self.fetch_all(conn, query, tuple(params))

    async def get_billing_record(self, conn: asyncpg.Connection, invoice_id: uuid.UUID) -> Optional[dict]:
        query = "SELECT * FROM invoices WHERE invoice_id = %s::uuid"
        return await self.fetch_one(conn, query, (invoice_id,))

    async def create_billing_record(
        self, 
        conn: asyncpg.Connection, 
        tenant_id: uuid.UUID, 
        amount: float, 
        currency: str, 
        status: str,
        stripe_invoice_id: Optional[str] = None,
        paypal_invoice_id: Optional[str] = None,
        paid_at: Optional[datetime] = None
    ) -> dict:
        query = """
            INSERT INTO invoices (invoice_id, tenant_id, amount, currency, status, stripe_invoice_id, paypal_invoice_id, paid_at, created_on, updated_on)
            VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
        """
        new_id = uuid.uuid4()
        now = datetime.now()
        return await self.execute_returning(conn, query, (new_id, tenant_id, amount, currency, status, stripe_invoice_id, paypal_invoice_id, paid_at, now, now))

    async def get_all_plans(self, conn: asyncpg.Connection) -> List[dict]:
        query = "SELECT * FROM subscription_plans"
        results = await self.fetch_all(conn, query)
        for row in results:
            if isinstance(row.get("limits"), str):
                try: row["limits"] = json.loads(row["limits"])
                except: row["limits"] = {}
        return results

    async def update_plan_stripe_ids(
        self, 
        conn: asyncpg.Connection, 
        plan_id: uuid.UUID, 
        monthly_id: Optional[str], 
        yearly_id: Optional[str]
    ) -> Optional[dict]:
        query = """
            UPDATE subscription_plans
            SET stripe_monthly_price_id = %s, stripe_yearly_price_id = %s, updated_on = %s
            WHERE plan_id = %s::uuid
            RETURNING *
        """
        return await self.execute_returning(conn, query, (monthly_id, yearly_id, datetime.now(), plan_id))

    async def upsert_subscription(
        self,
        conn: asyncpg.Connection,
        tenant_id: uuid.UUID,
        plan_id: uuid.UUID,
        status: str,
        stripe_subscription_id: Optional[str] = None,
        current_period_start: Optional[datetime] = None,
        current_period_end: Optional[datetime] = None,
        cancel_at_period_end: bool = False
    ) -> dict:
        # Check if subscription already exists for this tenant
        query_check = "SELECT subscription_id FROM subscriptions WHERE tenant_id = %s::uuid LIMIT 1"
        existing = await self.fetch_one(conn, query_check, (tenant_id,))
        
        if existing:
            query = """
                UPDATE subscriptions
                SET plan_id = %s::uuid,
                    status = %s,
                    stripe_subscription_id = %s,
                    current_period_start = %s,
                    current_period_end = %s,
                    cancel_at_period_end = %s,
                    updated_on = CURRENT_TIMESTAMP
                WHERE tenant_id = %s::uuid
                RETURNING *
            """
            return await self.execute_returning(conn, query, (
                plan_id, status, stripe_subscription_id, current_period_start, current_period_end, cancel_at_period_end, tenant_id
            ))
        else:
            query = """
                INSERT INTO subscriptions (
                    subscription_id, tenant_id, plan_id, status, stripe_subscription_id, current_period_start, current_period_end, cancel_at_period_end
                ) VALUES (
                    %s::uuid, %s::uuid, %s::uuid, %s, %s, %s, %s, %s
                ) RETURNING *
            """
            sub_id = uuid.uuid4()
            return await self.execute_returning(conn, query, (
                sub_id, tenant_id, plan_id, status, stripe_subscription_id, current_period_start, current_period_end, cancel_at_period_end
            ))

