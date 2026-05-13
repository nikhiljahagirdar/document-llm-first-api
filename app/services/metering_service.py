from typing import List, Dict, Any, Optional
import asyncpg
from datetime import datetime
import json
from app.db_raw import DBWrapper


class MeteringService:
    @staticmethod
    async def record_usage(
        conn: asyncpg.Connection,
        tenant_id: Any,
        metric_name: str,
        quantity: int = 1,
    ):
        """
        Record a new usage event for a tenant using raw SQL.
        """
        query = """
            INSERT INTO usage_logs (tenant_id, metric_name, quantity, created_on, updated_on)
            VALUES (%s::uuid, %s, %s, %s, %s)
            RETURNING *
        """
        now = datetime.now()
        return await DBWrapper.execute_returning(
            conn, query, (tenant_id, metric_name, quantity, now, now)
        )

    @staticmethod
    async def get_usage_summary(
        conn: asyncpg.Connection, tenant_id: Any
    ) -> List[Dict[str, Any]]:
        """
        Get a summary of all tracked metrics for a tenant's active subscription using raw SQL.
        """
        # 1. Get Active Subscription and Plan Limits
        sub_query = """
            SELECT s.current_period_start, p.limits 
            FROM subscriptions s 
            JOIN subscription_plans p ON s.plan_id::uuid = p.plan_id::uuid 
            WHERE s.tenant_id::uuid = %s::uuid AND s.status = 'active'
            LIMIT 1
        """
        sub = await DBWrapper.fetch_one(conn, sub_query, (tenant_id,))

        if not sub:
            return []

        period_start = sub["current_period_start"]
        limits = sub["limits"] or {}

        if not isinstance(limits, dict):
            try:
                limits = json.loads(limits) if isinstance(limits, str) else {}
            except:
                limits = {}

        # 2. Aggregate usage for all metrics in the plan
        usage_query = """
            SELECT metric_name, SUM(quantity) as total 
            FROM usage_logs 
            WHERE tenant_id::uuid = %s::uuid AND created_on >= %s 
            GROUP BY metric_name
        """
        usage_stats = await DBWrapper.fetch_all(
            conn, usage_query, (tenant_id, period_start)
        )
        usage_map = {item["metric_name"]: item["total"] for item in usage_stats}

        summary = []
        for metric, limit in limits.items():
            current_val = usage_map.get(metric, 0)
            summary.append(
                {
                    "metric_name": metric,
                    "total_quantity": int(current_val),
                    "limit": int(limit),
                    "usage_percent": round((current_val / limit) * 100, 2)
                    if limit > 0
                    else 0,
                }
            )

        return summary
