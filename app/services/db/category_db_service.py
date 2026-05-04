import psycopg
from typing import List, Optional
import uuid
from app.services.db.base_db_service import BaseDBService

class CategoryDBService(BaseDBService):
    async def list_categories(self, conn: psycopg.AsyncConnection, limit: int = 100, offset: int = 0, search: Optional[str] = None) -> List[dict]:
        query = """
            SELECT c.*, i.name as industry_name
            FROM categories c
            LEFT JOIN industries i ON c.industry_id = i.industry_id
        """
        params = []
        if search:
            query += " WHERE c.name ILIKE %s OR c.description ILIKE %s"
            params.extend([f"%{search}%", f"%{search}%"])
        query += " ORDER BY c.name LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        return await self.fetch_all(conn, query, tuple(params))

    async def get_category(self, conn: psycopg.AsyncConnection, category_id: uuid.UUID) -> Optional[dict]:
        query = "SELECT * FROM categories WHERE category_id = %s::uuid"
        return await self.fetch_one(conn, query, (category_id,))

    async def get_subcategories(self, conn: psycopg.AsyncConnection, category_id: uuid.UUID) -> List[dict]:
        query = "SELECT * FROM subcategories WHERE category_id = %s::uuid"
        return await self.fetch_all(conn, query, (category_id,))

    async def create_category(self, conn: psycopg.AsyncConnection, industry_id: uuid.UUID, name: str, description: str) -> dict:
        query = """
            INSERT INTO categories (category_id, industry_id, name, description)
            VALUES (%s::uuid, %s::uuid, %s, %s)
            RETURNING *
        """
        new_id = uuid.uuid4()
        return await self.execute_returning(conn, query, (new_id, industry_id, name, description))

    async def update_category(self, conn: psycopg.AsyncConnection, category_id: uuid.UUID, update_data: dict) -> Optional[dict]:
        if not update_data:
            return await self.get_category(conn, category_id)
        
        set_clause = ", ".join([f"{k} = %s" for k in update_data.keys()])
        query = f"UPDATE categories SET {set_clause}, updated_on = CURRENT_TIMESTAMP WHERE category_id = %s::uuid RETURNING *"
        params = list(update_data.values()) + [category_id]
        return await self.execute_returning(conn, query, tuple(params))

    async def delete_category(self, conn: psycopg.AsyncConnection, category_id: uuid.UUID) -> bool:
        query = "DELETE FROM categories WHERE category_id = %s::uuid RETURNING category_id"
        result = await self.fetch_one(conn, query, (category_id,))
        return result is not None
