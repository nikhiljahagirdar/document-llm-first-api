import psycopg
import json
from typing import List, Optional
import uuid
from app.services.db.base_db_service import BaseDBService

class PlanDBService(BaseDBService):
    async def list_plans(self, conn: psycopg.AsyncConnection, limit: int = 100, offset: int = 0, active_only: bool = True) -> List[dict]:
        query = "SELECT * FROM subscription_plans"
        params = []
        if active_only:
            query += " WHERE is_active = TRUE"
        query += " ORDER BY price LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        return await self.fetch_all(conn, query, tuple(params))

    async def get_plan(self, conn: psycopg.AsyncConnection, plan_id: uuid.UUID) -> Optional[dict]:
        query = "SELECT * FROM subscription_plans WHERE plan_id = %s::uuid"
        return await self.fetch_one(conn, query, (plan_id,))

    async def create_plan(self, conn: psycopg.AsyncConnection, plan_data: dict) -> dict:
        columns = ["plan_id"]
        values = [uuid.uuid4()]
        
        for k, v in plan_data.items():
            columns.append(k)
            values.append(json.dumps(v) if isinstance(v, (dict, list)) else v)

        placeholders = ["%s"] * len(columns)
        query = f"""
            INSERT INTO subscription_plans ({", ".join(columns)})
            VALUES ({", ".join(placeholders)})
            RETURNING *
        """
        return await self.execute_returning(conn, query, tuple(values))

    async def update_plan(self, conn: psycopg.AsyncConnection, plan_id: uuid.UUID, update_data: dict) -> Optional[dict]:
        if not update_data:
            return await self.get_plan(conn, plan_id)
        
        processed_data = {}
        for k, v in update_data.items():
            if isinstance(v, (dict, list)):
                processed_data[k] = json.dumps(v)
            else:
                processed_data[k] = v

        set_clause = ", ".join([f"{k} = %s" for k in processed_data.keys()])
        query = f"UPDATE subscription_plans SET {set_clause}, updated_on = CURRENT_TIMESTAMP WHERE plan_id = %s::uuid RETURNING *"
        params = list(processed_data.values()) + [plan_id]
        return await self.execute_returning(conn, query, tuple(params))

    async def delete_plan(self, conn: psycopg.AsyncConnection, plan_id: uuid.UUID) -> bool:
        query = "DELETE FROM subscription_plans WHERE plan_id = %s::uuid RETURNING plan_id"
        result = await self.fetch_one(conn, query, (plan_id,))
        return result is not None
