import asyncpg
from typing import List, Optional
import uuid
from app.services.db.base_db_service import BaseDBService

class IndustryDBService(BaseDBService):
    INDUSTRY_HIERARCHY_QUERY = """
    SELECT
        i.industry_id, i.name, i.description, i.icon,

        COALESCE(
            (SELECT json_agg(c_data)
             FROM (
                SELECT 
                    c.category_id, c.industry_id, c.name, c.description,
                    COALESCE(
                        (SELECT json_agg(sc_data) FROM (
                            SELECT subcategory_id, category_id, name, description FROM subcategories WHERE category_id = c.category_id
                        ) sc_data),
                        '[]'::json
                    )::jsonb as subcategories
                FROM categories c
                WHERE c.industry_id = i.industry_id
             ) c_data
            ),
            '[]'::json
        )::jsonb as categories
    FROM industries i
    """

    async def list_industries(self, conn: asyncpg.Connection, search: Optional[str] = None) -> List[dict]:
        query = self.INDUSTRY_HIERARCHY_QUERY
        params = []
        if search:
            query += " WHERE i.name ILIKE %s"
            params.append(f"%{search}%")
        query += " ORDER BY i.name"
        return await self.fetch_all(conn, query, tuple(params))

    async def get_industry(self, conn: asyncpg.Connection, industry_id: uuid.UUID) -> Optional[dict]:
        query = self.INDUSTRY_HIERARCHY_QUERY + " WHERE i.industry_id = %s::uuid"
        return await self.fetch_one(conn, query, (industry_id,))

    async def create_industry(self, conn: asyncpg.Connection, industry_data: dict) -> dict:
        industry_id = uuid.uuid4()
        
        columns = ["industry_id"] + list(industry_data.keys())
        placeholders = ["%s::uuid"] + ["%s"] * len(industry_data)
        values = [industry_id] + list(industry_data.values())
        
        query = f"INSERT INTO industries ({', '.join(columns)}) VALUES ({', '.join(placeholders)})"
        await self.execute(conn, query, tuple(values))
        return await self.get_industry(conn, industry_id)

    async def update_industry(self, conn: asyncpg.Connection, industry_id: uuid.UUID, update_data: dict) -> Optional[dict]:
        if update_data:
            set_clause = ", ".join([f"{k} = %s" for k in update_data.keys()])
            params = list(update_data.values())
            params.append(industry_id)
            await self.execute(conn, f"UPDATE industries SET {set_clause}, updated_on = NOW() WHERE industry_id = %s::uuid", tuple(params))
        
        return await self.get_industry(conn, industry_id)

    async def delete_industry(self, conn: asyncpg.Connection, industry_id: uuid.UUID) -> bool:
        await self.execute(conn, "DELETE FROM industries WHERE industry_id = %s::uuid", (industry_id,))
        return True

    async def get_industry_templates(self, conn: asyncpg.Connection, industry_id: uuid.UUID, tenant_id: Optional[uuid.UUID] = None) -> List[dict]:
        query = "SELECT * FROM templates WHERE industry_id = %s::uuid"
        if tenant_id:
            query += " AND (tenant_id = %s::uuid OR is_public = TRUE)"
            params = (industry_id, tenant_id)
        else:
            query += " AND is_public = TRUE"
            params = (industry_id,)
        return await self.fetch_all(conn, query, params)
