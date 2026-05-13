import uuid
from datetime import datetime
from typing import List, Optional
import asyncpg
from app.services.db.base_db_service import BaseDBService

class NotificationDBService(BaseDBService):
    async def list_notifications(
        self, 
        conn: asyncpg.Connection, 
        user_id: uuid.UUID, 
        limit: int = 50, 
        offset: int = 0, 
        status: str = "all"
    ) -> List[dict]:
        """
        List notifications with filters for all, read, or unread.
        """
        query = "SELECT * FROM notifications WHERE user_id::uuid = %s::uuid AND is_active = TRUE"
        params = [user_id]
        
        if status == "unread":
            query += " AND is_read = FALSE"
        elif status == "read":
            query += " AND is_read = TRUE"
        # "all" is the default (no extra where clause)

        query += " ORDER BY created_on DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        return await self.fetch_all(conn, query, tuple(params))

    async def mark_as_read(self, conn: asyncpg.Connection, notification_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        query = "UPDATE notifications SET is_read = TRUE, updated_on = NOW() WHERE notification_id::uuid = %s::uuid AND user_id::uuid = %s::uuid AND is_active = TRUE RETURNING 1"
        result = await self.fetch_one(conn, query, (notification_id, user_id))
        return result is not None

    async def mark_all_as_read(self, conn: asyncpg.Connection, user_id: uuid.UUID):
        query = "UPDATE notifications SET is_read = TRUE, updated_on = NOW() WHERE user_id::uuid = %s::uuid AND is_read = FALSE AND is_active = TRUE"
        await self.execute(conn, query, (user_id,))

    async def create_notification(self, conn: asyncpg.Connection, user_id: uuid.UUID, title: str, message: str, type: str = "info") -> dict:
        query = """
            INSERT INTO notifications (notification_id, user_id, title, message, type, is_read, is_active, created_on, updated_on)
            VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
        """
        new_id = uuid.uuid4()
        now = datetime.now()
        return await self.execute_returning(conn, query, (new_id, user_id, title, message, type, False, True, now, now))

    async def delete_notification(self, conn: asyncpg.Connection, notification_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        query = "UPDATE notifications SET is_active = FALSE, updated_on = NOW() WHERE notification_id::uuid = %s::uuid AND user_id::uuid = %s::uuid RETURNING 1"
        result = await self.fetch_one(conn, query, (notification_id, user_id))
        return result is not None
