import asyncpg
import json
from typing import List, Optional
import uuid
from datetime import datetime
from app.services.db.base_db_service import BaseDBService

class TemplateDBService(BaseDBService):
    TEMPLATE_HIERARCHY_QUERY = """
    SELECT 
        t.*,
        (SELECT row_to_json(i_data)::jsonb FROM (SELECT industry_id, name FROM industries WHERE industry_id = t.industry_id) i_data) as industry,
        (SELECT row_to_json(c_data)::jsonb FROM (SELECT category_id, name FROM categories WHERE category_id = t.category_id) c_data) as category_rel,
        (SELECT row_to_json(s_data)::jsonb FROM (SELECT subcategory_id, name FROM subcategories WHERE subcategory_id = t.subcategory_id) s_data) as subcategory_rel
    FROM templates t
    """

    async def list_public_templates(self, conn: asyncpg.Connection, limit: int = 20, offset: int = 0, industry_id: Optional[uuid.UUID] = None, category_id: Optional[uuid.UUID] = None, subcategory_id: Optional[uuid.UUID] = None, search: Optional[str] = None) -> List[dict]:
        query = self.TEMPLATE_HIERARCHY_QUERY + " WHERE t.is_public = TRUE"
        params = []
        if industry_id:
            query += " AND t.industry_id = %s::uuid"
            params.append(industry_id)
        if category_id:
            query += " AND t.category_id = %s::uuid"
            params.append(category_id)
        if subcategory_id:
            query += " AND t.subcategory_id = %s::uuid"
            params.append(subcategory_id)
        if search:
            query += " AND (t.template_name ILIKE %s OR t.description ILIKE %s)"
            params.extend([f"%{search}%", f"%{search}%"])
        query += " ORDER BY t.template_name LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        return await self.fetch_all(conn, query, tuple(params))

    async def list_user_templates(self, conn: asyncpg.Connection, tenant_id: uuid.UUID) -> List[dict]:
        query = self.TEMPLATE_HIERARCHY_QUERY + " WHERE t.tenant_id = %s::uuid OR t.is_public = TRUE"
        return await self.fetch_all(conn, query, (tenant_id,))

    async def get_template(self, conn: asyncpg.Connection, template_id: uuid.UUID) -> Optional[dict]:
        query = self.TEMPLATE_HIERARCHY_QUERY + " WHERE t.template_id = %s::uuid"
        return await self.fetch_one(conn, query, (template_id,))

    async def create_template(self, conn: asyncpg.Connection, template_data: dict) -> dict:
        template_id = uuid.uuid4()
        columns = ["template_id"] + list(template_data.keys())
        placeholders = ["%s::uuid"] + ["%s"] * len(template_data)
        values = [template_id]
        for v in template_data.values():
            if isinstance(v, (dict, list)):
                values.append(json.dumps(v))
            else:
                values.append(v)
        
        query = f"INSERT INTO templates ({', '.join(columns)}) VALUES ({', '.join(placeholders)})"
        await self.execute(conn, query, tuple(values))
        return await self.get_template(conn, template_id)

    async def update_template(self, conn: asyncpg.Connection, template_id: uuid.UUID, update_data: dict) -> Optional[dict]:
        if update_data:
            set_clause = ", ".join([f"{k} = %s" for k in update_data.keys()])
            values = []
            for v in update_data.values():
                if isinstance(v, (dict, list)):
                    values.append(json.dumps(v))
                else:
                    values.append(v)
            values.append(template_id)
            query = f"UPDATE templates SET {set_clause}, updated_on = CURRENT_TIMESTAMP WHERE template_id = %s::uuid"
            await self.execute(conn, query, tuple(values))
        return await self.get_template(conn, template_id)

    async def delete_template(self, conn: asyncpg.Connection, template_id: uuid.UUID, tenant_id: uuid.UUID) -> bool:
        # Check ownership
        check_query = "SELECT 1 FROM templates WHERE template_id = %s::uuid AND tenant_id = %s::uuid"
        if not await self.fetch_one(conn, check_query, (template_id, tenant_id)):
            return False
        
        await self.execute(conn, "DELETE FROM templates WHERE template_id = %s::uuid", (template_id,))
        return True
