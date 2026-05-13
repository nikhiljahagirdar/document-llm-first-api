import asyncpg
from typing import List, Optional
import uuid
from app.services.db.base_db_service import BaseDBService

class SubcategoryDBService(BaseDBService):
    async def list_subcategories(self, conn: asyncpg.Connection, limit: int = 100, offset: int = 0, search: Optional[str] = None) -> List[dict]:
        query = """
            SELECT sc.*, c.name as category_name
            FROM subcategories sc
            LEFT JOIN categories c ON sc.category_id = c.category_id
        """
        params = []
        if search:
            query += " WHERE sc.name ILIKE %s OR sc.description ILIKE %s"
            params.extend([f"%{search}%", f"%{search}%"])
        query += " ORDER BY sc.name LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        return await self.fetch_all(conn, query, tuple(params))

    async def get_all_subcategories_with_parents(self, conn: asyncpg.Connection) -> List[dict]:
        """Fetch all subcategories with their parent category and industry info."""
        query = """
            SELECT 
                sc.subcategory_id, sc.name as subcategory_name, 
                c.category_id, c.name as category_name, 
                i.industry_id, i.name as industry_name
            FROM subcategories sc
            JOIN categories c ON sc.category_id = c.category_id
            JOIN industries i ON c.industry_id = i.industry_id
            ORDER BY i.name, c.name, sc.name
        """
        return await self.fetch_all(conn, query)

    async def get_subcategory(self, conn: asyncpg.Connection, subcategory_id: uuid.UUID) -> Optional[dict]:
        query = "SELECT * FROM subcategories WHERE subcategory_id = %s::uuid"
        return await self.fetch_one(conn, query, (subcategory_id,))

    async def create_subcategory(self, conn: asyncpg.Connection, category_id: uuid.UUID, name: str, description: Optional[str] = None, prompt: Optional[str] = None) -> dict:
        query = """
            INSERT INTO subcategories (subcategory_id, category_id, name, description, prompt)
            VALUES (%s::uuid, %s::uuid, %s, %s, %s)
            RETURNING *
        """
        new_id = uuid.uuid4()
        return await self.execute_returning(conn, query, (new_id, category_id, name, description, prompt))

    async def update_subcategory(self, conn: asyncpg.Connection, subcategory_id: uuid.UUID, update_data: dict) -> Optional[dict]:
        if not update_data:
            return await self.get_subcategory(conn, subcategory_id)
        
        set_clause = ", ".join([f"{k} = %s" for k in update_data.keys()])
        query = f"UPDATE subcategories SET {set_clause}, updated_on = CURRENT_TIMESTAMP WHERE subcategory_id = %s::uuid RETURNING *"
        params = list(update_data.values()) + [subcategory_id]
        return await self.execute_returning(conn, query, tuple(params))

    async def delete_subcategory(self, conn: asyncpg.Connection, subcategory_id: uuid.UUID) -> bool:
        query = "DELETE FROM subcategories WHERE subcategory_id = %s::uuid RETURNING subcategory_id"
        result = await self.fetch_one(conn, query, (subcategory_id,))
        return result is not None
