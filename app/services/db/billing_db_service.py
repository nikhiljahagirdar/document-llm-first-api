import psycopg
from typing import List, Optional
import uuid
from datetime import datetime
from app.services.db.base_db_service import BaseDBService

class BillingDBService(BaseDBService):
    async def get_tenant_subscription(self, conn: psycopg.AsyncConnection, tenant_id: uuid.UUID) -> Optional[dict]:
        query = """
            SELECT s.*, row_to_json(p_data) as plan
            FROM subscriptions s
            LEFT JOIN (SELECT plan_id, name, description, price, currency, interval as billing_cycle, limits FROM subscription_plans) p_data 
            ON s.plan_id = p_data.plan_id
            WHERE s.tenant_id = %s::uuid
            LIMIT 1
        """
        return await self.fetch_one(conn, query, (tenant_id,))

    async def get_any_plan_id(self, conn: psycopg.AsyncConnection) -> Optional[uuid.UUID]:
        query = "SELECT plan_id FROM subscription_plans LIMIT 1"
        result = await self.fetch_one(conn, query)
        return result["plan_id"] if result else None

    async def create_trial_subscription(self, conn: psycopg.AsyncConnection, tenant_id: uuid.UUID, plan_id: uuid.UUID) -> None:
        query = "INSERT INTO subscriptions (tenant_id, plan_id, status) VALUES (%s::uuid, %s::uuid, 'trial')"
        await self.execute(conn, query, (tenant_id, plan_id))

    async def get_plan_by_id(self, conn: psycopg.AsyncConnection, plan_id: uuid.UUID) -> Optional[dict]:
        query = "SELECT * FROM subscription_plans WHERE plan_id = %s::uuid"
        return await self.fetch_one(conn, query, (plan_id,))

    async def list_billing_records(self, conn: psycopg.AsyncConnection, tenant_id: uuid.UUID, limit: int = 100, offset: int = 0, search: Optional[str] = None) -> List[dict]:
        query = "SELECT * FROM invoices WHERE tenant_id = %s::uuid"
        params = [tenant_id]
        if search:
            query += " AND (stripe_invoice_id ILIKE %s OR paypal_invoice_id ILIKE %s OR status ILIKE %s OR CAST(amount AS TEXT) ILIKE %s)"
            params.extend([f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%"])
        query += " ORDER BY created_on DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        return await self.fetch_all(conn, query, tuple(params))

    async def get_billing_record(self, conn: psycopg.AsyncConnection, invoice_id: uuid.UUID) -> Optional[dict]:
        query = "SELECT * FROM invoices WHERE invoice_id = %s::uuid"
        return await self.fetch_one(conn, query, (invoice_id,))

    async def create_billing_record(
        self, 
        conn: psycopg.AsyncConnection, 
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

