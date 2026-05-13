import uuid
from datetime import datetime
from typing import Optional, List, Any
import asyncpg
from app.services.db.base_db_service import BaseDBService

class FolderDBService(BaseDBService):
    async def create_folder(
        self,
        conn: asyncpg.Connection,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str,
        description: Optional[str] = None,
        parent_folder_id: Optional[uuid.UUID] = None,
    ) -> dict:
        folder_id = uuid.uuid4()
        now = datetime.now()
        query = """
            INSERT INTO folders (folder_id, tenant_id, user_id, parent_folder_id, name, description, created_on, updated_on)
            VALUES (%s::uuid, %s::uuid, %s::uuid, %s::uuid, %s, %s, %s, %s)
            RETURNING *
        """
        return await self.execute_returning(
            conn,
            query,
            (folder_id, tenant_id, user_id, parent_folder_id, name, description, now, now),
        )

    async def get_folder(
        self,
        conn: asyncpg.Connection,
        folder_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> Optional[dict]:
        query = "SELECT * FROM folders WHERE folder_id = %s::uuid AND tenant_id = %s::uuid"
        return await self.fetch_one(conn, query, (folder_id, tenant_id))

    async def list_folders(
        self,
        conn: asyncpg.Connection,
        tenant_id: uuid.UUID,
        parent_folder_id: Optional[uuid.UUID] = None,
        search: Optional[str] = None
    ) -> List[dict]:
        query = "SELECT * FROM folders WHERE tenant_id = %s::uuid"
        params = [tenant_id]
        
        if parent_folder_id:
            query += " AND parent_folder_id = %s::uuid"
            params.append(parent_folder_id)
        elif parent_folder_id is None and not search:
            query += " AND parent_folder_id IS NULL"

        if search:
            query += " AND name ILIKE %s"
            params.append(f"%{search}%")

        query += " ORDER BY name ASC"
        return await self.fetch_all(conn, query, tuple(params))

    async def update_folder(
        self,
        conn: asyncpg.Connection,
        folder_id: uuid.UUID,
        tenant_id: uuid.UUID,
        data: dict
    ) -> dict:
        data["updated_on"] = datetime.now()
        return await self.update_record(
            conn, "folders", {"folder_id": folder_id, "tenant_id": tenant_id}, data
        )

    async def delete_folder(
        self,
        conn: asyncpg.Connection,
        folder_id: uuid.UUID,
        tenant_id: uuid.UUID
    ) -> bool:
        # Check for children (subfolders or documents)
        subfolders = await self.fetch_one(conn, "SELECT 1 FROM folders WHERE parent_folder_id = %s::uuid", (folder_id,))
        docs = await self.fetch_one(conn, "SELECT 1 FROM documents WHERE folder_id = %s::uuid", (folder_id,))
        
        if subfolders or docs:
             raise Exception("Folder is not empty")

        query = "DELETE FROM folders WHERE folder_id = %s::uuid AND tenant_id = %s::uuid"
        await self.execute(conn, query, (folder_id, tenant_id))
        return True
