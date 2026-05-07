import psycopg
from typing import List, Optional
import uuid
from datetime import datetime
from app.services.db.base_db_service import BaseDBService

class MeteringDBService(BaseDBService):
    async def list_metering_records(
        self, 
        conn: psycopg.AsyncConnection, 
        tenant_id: uuid.UUID, 
        limit: int = 100, 
        offset: int = 0, 
        search: Optional[str] = None,
        user_id: Optional[uuid.UUID] = None
    ) -> List[dict]:
        query = "SELECT * FROM usage_logs WHERE tenant_id::uuid = %s::uuid"
        params = [tenant_id]
        
        if user_id:
            query += " AND user_id::uuid = %s::uuid"
            params.append(user_id)
            
        if search:
            query += " AND metric_name ILIKE %s"
            params.append(f"%{search}%")
            
        query += " ORDER BY created_on DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        return await self.fetch_all(conn, query, tuple(params))

    async def get_usage_summary(
        self, 
        conn: psycopg.AsyncConnection, 
        tenant_id: uuid.UUID, 
        user_id: Optional[uuid.UUID] = None,
        role_name: str = "user"
    ) -> List[dict]:
        # Normalize role name
        role_key = role_name.lower().replace(" ", "_")
        
        is_superadmin = role_key == "super_admin" or role_key == "superadmin"
        # All roles in a tenant should see the tenant-wide usage against the plan limits
        # Only superadmin sees the global (across all tenants) summary.

        # 1. Get Subscription and Plan Limits
        if is_superadmin:
            # Aggregate limits across all active/trial subscriptions
            query = """
                SELECT 
                    SUM(CASE WHEN (p.limits->>'ai_limit')::numeric = -1 THEN 1000000000 ELSE COALESCE((p.limits->>'ai_limit')::numeric, 0) END) as ai_limit,
                    SUM(CASE WHEN (p.limits->>'ocr_pages')::numeric = -1 THEN 1000000 ELSE COALESCE((p.limits->>'ocr_pages')::numeric, 0) END) as ocr_pages,
                    SUM(CASE WHEN (p.limits->>'storage_limit_mb')::numeric = -1 THEN 1048576 ELSE COALESCE((p.limits->>'storage_limit_mb')::numeric, 0) END) as storage_limit_mb,
                    SUM(CASE WHEN (p.limits->>'doc_limit')::numeric = -1 THEN 1000000 ELSE COALESCE((p.limits->>'doc_limit')::numeric, 0) END) as doc_limit
                FROM subscriptions s 
                JOIN subscription_plans p ON s.plan_id::uuid = p.plan_id::uuid 
                WHERE s.status IN ('active', 'trial')
            """
            limits_res = await self.fetch_one(conn, query)
            plan_limits = {
                "ai_limit": float(limits_res["ai_limit"]) if limits_res and limits_res.get("ai_limit") else 1000000,
                "ocr_pages": float(limits_res["ocr_pages"]) if limits_res and limits_res.get("ocr_pages") else 1000,
                "storage_limit_mb": float(limits_res["storage_limit_mb"]) if limits_res and limits_res.get("storage_limit_mb") else 1024,
                "doc_limit": float(limits_res["doc_limit"]) if limits_res and limits_res.get("doc_limit") else 10000
            }
            start_date = datetime.min
        else:
            query = """
                SELECT s.*, p.limits 
                FROM subscriptions s 
                JOIN subscription_plans p ON s.plan_id::uuid = p.plan_id::uuid 
                WHERE s.tenant_id::uuid = %s::uuid AND s.status IN ('active', 'trial')
                LIMIT 1
            """
            subscription = await self.fetch_one(conn, query, (tenant_id,))
            if subscription:
                start_date = subscription.get("current_period_start") or datetime.min
                plan_limits = subscription.get("limits") or {}
                if isinstance(plan_limits, str):
                    import json
                    try: plan_limits = json.loads(plan_limits)
                    except: plan_limits = {}
            else:
                # Fallback: Use default limits if no subscription found
                # This ensures the dashboard doesn't show an empty list
                start_date = datetime.min
                plan_limits = {
                    "ai_limit": 10000,
                    "ocr_pages": 10,
                    "storage_limit_mb": 100,
                    "doc_limit": 100
                }
                # Try to get a more realistic start_date (e.g. beginning of current month)
                from datetime import date
                start_date = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # 2. Get AI & OCR Usage from logs (Tenant-wide for summary)
        if is_superadmin:
            usage_query = "SELECT metric_name, SUM(quantity) as total FROM usage_logs GROUP BY metric_name"
            usage_stats = await self.fetch_all(conn, usage_query)
        else:
            usage_query = """
                SELECT metric_name, SUM(quantity) as total 
                FROM usage_logs 
                WHERE tenant_id::uuid = %s::uuid AND created_on >= %s 
                GROUP BY metric_name
            """
            usage_stats = await self.fetch_all(conn, usage_query, (tenant_id, start_date))

        # 3. Get Storage Usage and Document Counts (Tenant-wide for summary)
        if is_superadmin:
            storage_query = "SELECT SUM(file_size) as total_size, COUNT(*) as total_docs FROM documents WHERE is_active = TRUE"
            storage_res = await self.fetch_one(conn, storage_query)
        else:
            storage_query = "SELECT SUM(file_size) as total_size, COUNT(*) as total_docs FROM documents WHERE tenant_id::uuid = %s::uuid AND is_active = TRUE"
            storage_res = await self.fetch_one(conn, storage_query, (tenant_id,))
        
        total_storage_bytes = storage_res["total_size"] if storage_res and storage_res.get("total_size") else 0
        total_storage_mb = round(total_storage_bytes / (1024 * 1024), 2)
        total_docs_count = storage_res["total_docs"] if storage_res and storage_res.get("total_docs") else 0

        # 4. Extraction Rate and Latency
        extraction_rate = 0.0
        avg_latency = 0.0
        if is_superadmin:
            # Global Extraction Rate
            res_proc = await self.fetch_one(conn, "SELECT COUNT(*) as count FROM documents WHERE status = 'completed'")
            total_processed = res_proc["count"] if res_proc else 0
            res_total = await self.fetch_one(conn, "SELECT COUNT(*) as count FROM documents")
            all_docs = res_total["count"] if res_total else 0
            extraction_rate = (total_processed / all_docs * 100) if all_docs > 0 else 100.0

            # Global Edge Latency
            latency_query = """
                SELECT AVG(EXTRACT(EPOCH FROM (p.created_on - e.created_on))) as avg_latency
                FROM document_statuses e
                JOIN document_statuses p ON e.document_id = p.document_id
                WHERE e.status = 'processing' AND p.status = 'completed'
            """
            res_lat = await self.fetch_one(conn, latency_query)
            avg_latency = float(res_lat["avg_latency"]) if res_lat and res_lat.get("avg_latency") else 1.25
        else:
            # Tenant Extraction Rate
            res_proc = await self.fetch_one(conn, "SELECT COUNT(*) as count FROM documents WHERE tenant_id::uuid = %s::uuid AND status = 'completed'", (tenant_id,))
            total_processed = res_proc["count"] if res_proc else 0
            res_total = await self.fetch_one(conn, "SELECT COUNT(*) as count FROM documents WHERE tenant_id::uuid = %s::uuid", (tenant_id,))
            all_docs = res_total["count"] if res_total else 0
            extraction_rate = (total_processed / all_docs * 100) if all_docs > 0 else 100.0

            # Tenant Edge Latency
            latency_query = """
                SELECT AVG(EXTRACT(EPOCH FROM (p.created_on - e.created_on))) as avg_latency
                FROM document_statuses e
                JOIN document_statuses p ON e.document_id = p.document_id
                JOIN documents d ON e.document_id = d.document_id
                WHERE d.tenant_id::uuid = %s::uuid AND e.status = 'processing' AND p.status = 'completed'
            """
            res_lat = await self.fetch_one(conn, latency_query, (tenant_id,))
            avg_latency = float(res_lat["avg_latency"]) if res_lat and res_lat.get("avg_latency") else 1.25

        # 5. Process Limits and Map to professional names
        usage_map = {item["metric_name"]: item["total"] for item in usage_stats}
        
        ai_used = (usage_map.get("AI Usage (Tokens)", 0) or 0) + (usage_map.get("total_tokens", 0) or 0) + (usage_map.get("prompt_tokens", 0) or 0) + (usage_map.get("candidate_tokens", 0) or 0)
        ocr_used = (usage_map.get("OCR Usage (Pages)", 0) or 0) + (usage_map.get("ocr_pages", 0) or 0)

        def calculate_percent(used, limit):
            if limit == -1 or limit >= 1000000000: return 0.0
            if not limit: return 0.0
            return round((used / limit) * 100, 2)

        # Limits mapping
        summary = [
            {
                "metric_name": "AI Usage (Tokens)",
                "total_quantity": float(ai_used),
                "limit": int(plan_limits.get("ai_limit", 1000000)),
                "usage_percent": calculate_percent(ai_used, int(plan_limits.get("ai_limit", 1000000)))
            },
            {
                "metric_name": "OCR Usage (Pages)",
                "total_quantity": float(ocr_used),
                "limit": int(plan_limits.get("ocr_pages", 1000)),
                "usage_percent": calculate_percent(ocr_used, int(plan_limits.get("ocr_pages", 1000)))
            },
            {
                "metric_name": "Storage Usage (MB)",
                "total_quantity": total_storage_mb,
                "limit": int(plan_limits.get("storage_limit_mb", 1024)),
                "usage_percent": calculate_percent(total_storage_mb, int(plan_limits.get("storage_limit_mb", 1024)))
            },
            {
                "metric_name": "Total Documents",
                "total_quantity": float(total_docs_count),
                "limit": int(plan_limits.get("doc_limit", 10000)) if plan_limits.get("doc_limit") else None,
                "usage_percent": calculate_percent(total_docs_count, int(plan_limits.get("doc_limit", 10000))) if plan_limits.get("doc_limit") else None
            },
            {
                "metric_name": "Average Extraction Rate (%)",
                "total_quantity": round(extraction_rate, 2),
                "limit": 100,
                "usage_percent": round(extraction_rate, 2)
            },
            {
                "metric_name": "Edge Latency (Seconds)",
                "total_quantity": round(avg_latency, 2),
                "limit": None,
                "usage_percent": None
            }
        ]
        
        return summary

    async def create_metering_record(
        self, 
        conn: psycopg.AsyncConnection, 
        tenant_id: uuid.UUID, 
        metric_name: str, 
        quantity: int = 1,
        user_id: Optional[uuid.UUID] = None
    ) -> dict:
        query = """
            INSERT INTO usage_logs (log_id, tenant_id, user_id, metric_name, quantity, created_on, updated_on)
            VALUES (%s::uuid, %s::uuid, %s::uuid, %s, %s, %s, %s)
            RETURNING *
        """
        new_id = uuid.uuid4()
        now = datetime.now()
        return await self.execute_returning(conn, query, (new_id, tenant_id, user_id, metric_name, quantity, now, now))

    async def check_usage_limits(
        self, 
        conn: psycopg.AsyncConnection, 
        tenant_id: uuid.UUID, 
        metric_type: str = "ai" # "ai", "ocr", or "storage"
    ):
        """
        Checks if the tenant has exceeded their plan limits.
        If no subscription exists, allows the operation (no limits enforced).
        """
        try:
            summary = await self.get_usage_summary(conn, tenant_id, role_name="tenant_admin")
        except Exception:
            return  # No subscription or DB error — allow operation
        if not summary:
            return  # No subscription — allow operation

        target_metric = None
        if metric_type == "ai":
            target_metric = next((m for m in summary if "AI" in m["metric_name"]), None)
        elif metric_type == "ocr":
            target_metric = next((m for m in summary if "OCR" in m["metric_name"]), None)
        elif metric_type == "storage":
            target_metric = next((m for m in summary if "Storage" in m["metric_name"]), None)

        if not target_metric:
            return

        percent = target_metric["usage_percent"]
        metric_name = target_metric["metric_name"]

        # 1. Block if limit reached
        if percent >= 100:
            raise Exception(f"LIMIT REACHED: You have used 100% of your {metric_name} allowance. Operation cancelled.")

        # 2. Notify if approaching limit (90%)
        if percent >= 90:
            from app.services.notification_service import NotificationService
            try:
                # Find a tenant admin to notify
                admin_res = await self.fetch_one(conn, "SELECT u.user_id FROM users u JOIN roles r ON u.role_id = r.role_id WHERE u.tenant_id = %s AND r.name = 'tenant_admin' LIMIT 1", (tenant_id,))
                if admin_res:
                    admin_id = admin_res["user_id"]
                    await NotificationService.send_notification(
                        str(admin_id),
                        f"⚠️ Usage Alert: {metric_name}",
                        f"You have used {percent}% of your {metric_name} limit. Work will stop once you reach 100%.",
                        "warning"
                    )
            except Exception as e:
                print(f"FAILED TO SEND LIMIT NOTIFICATION: {e}")

        return True
