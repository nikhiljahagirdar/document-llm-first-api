import asyncpg
from typing import List, Optional, Any
import uuid
from datetime import datetime, timedelta
from app.services.db.base_db_service import BaseDBService

class AdminDBService(BaseDBService):
    async def get_platform_metrics(self, conn: asyncpg.Connection) -> dict:
        """
        Retrieve comprehensive platform metrics.
        """
        # Summary Metrics
        tenants_count = await self.fetch_one(conn, "SELECT COUNT(*) as count FROM tenants")
        users_count = await self.fetch_one(conn, "SELECT COUNT(*) as count FROM users")
        docs_count = await self.fetch_one(conn, "SELECT COUNT(*) as count FROM documents")
        revenue = await self.fetch_one(conn, "SELECT SUM(amount) as total FROM invoices WHERE status = 'paid'")
        active_subs = await self.fetch_one(conn, "SELECT COUNT(*) as count FROM subscriptions WHERE status = 'active'")
        
        # Growth (last 24h)
        yesterday = datetime.now() - timedelta(days=1)
        new_tenants = await self.fetch_one(conn, "SELECT COUNT(*) as count FROM tenants WHERE created_on >= %s", (yesterday,))
        new_users = await self.fetch_one(conn, "SELECT COUNT(*) as count FROM users WHERE created_on >= %s", (yesterday,))
        new_docs = await self.fetch_one(conn, "SELECT COUNT(*) as count FROM documents WHERE created_on >= %s", (yesterday,))

        # Data for Graphs (Last 30 Days)
        thirty_days_ago = datetime.now() - timedelta(days=30)
        
        daily_revenue = await self.fetch_all(conn, """
            SELECT DATE(created_on) as date, SUM(amount) as total 
            FROM invoices 
            WHERE status = 'paid' AND created_on >= %s 
            GROUP BY DATE(created_on) ORDER BY date
        """, (thirty_days_ago,))

        daily_signups = await self.fetch_all(conn, """
            SELECT DATE(created_on) as date, COUNT(*) as count 
            FROM tenants 
            WHERE created_on >= %s 
            GROUP BY DATE(created_on) ORDER BY date
        """, (thirty_days_ago,))

        plan_dist = await self.fetch_all(conn, """
            SELECT p.name, COUNT(s.subscription_id) as count 
            FROM subscription_plans p 
            LEFT JOIN subscriptions s ON p.plan_id = s.plan_id AND s.status = 'active'
            GROUP BY p.name
        """)

        return {
            "summary": {
                "total_tenants": tenants_count["count"],
                "total_users": users_count["count"],
                "total_documents": docs_count["count"],
                "total_revenue": float(revenue["total"] or 0),
                "active_subscriptions": active_subs["count"]
            },
            "growth_24h": {
                "new_tenants": new_tenants["count"],
                "new_users": new_users["count"],
                "new_documents": new_docs["count"]
            },
            "graphs": {
                "daily_revenue": [{"date": str(d["date"]), "total": float(d["total"])} for d in daily_revenue],
                "daily_signups": [{"date": str(d["date"]), "count": int(d["count"])} for d in daily_signups],
                "plan_distribution": [{"name": p["name"], "count": int(p["count"])} for p in plan_dist]
            },
            "system": {
                "database": "healthy",
                "version": "3.1.0"
            }
        }

    async def get_failed_payments(self, conn: asyncpg.Connection, limit: int = 50, offset: int = 0) -> List[dict]:
        query = "SELECT * FROM invoices WHERE status = 'failed' ORDER BY created_on DESC LIMIT %s OFFSET %s"
        return await self.fetch_all(conn, query, (limit, offset))

    async def list_all_tenants(self, conn: asyncpg.Connection, search: Optional[str] = None, limit: int = 20, offset: int = 0) -> List[dict]:
        query = """
            SELECT t.*, s.status as subscription_status, p.name as plan_name
            FROM tenants t
            LEFT JOIN subscriptions s ON t.tenant_id = s.tenant_id
            LEFT JOIN subscription_plans p ON s.plan_id = p.plan_id
        """
        params = []
        if search:
            query += " WHERE t.name ILIKE %s OR t.slug ILIKE %s"
            params.extend([f"%{search}%", f"%{search}%"])
        
        query += " ORDER BY t.created_on DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        
        return await self.fetch_all(conn, query, tuple(params))

    async def suspend_tenant(self, conn: asyncpg.Connection, tenant_id: str) -> bool:
        existing = await self.fetch_one(conn, "SELECT 1 FROM tenants WHERE tenant_id::uuid = %s::uuid", (tenant_id,))
        if not existing:
            return False
        await self.execute(conn, "UPDATE tenants SET is_active = FALSE WHERE tenant_id::uuid = %s::uuid", (tenant_id,))
        return True
