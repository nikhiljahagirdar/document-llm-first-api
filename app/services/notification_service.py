from typing import List, Dict
from fastapi import WebSocket
import json
import uuid
import asyncio
from datetime import datetime
from app.db_raw import DBWrapper

class ConnectionManager:
    def __init__(self):
        # Maps user_id to a list of active WebSockets on THIS instance
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, user_id: str, websocket: WebSocket):
        try:
            await websocket.accept()
            
            user_id_str = str(user_id)
            if user_id_str not in self.active_connections:
                self.active_connections[user_id_str] = []
            self.active_connections[user_id_str].append(websocket)
            print(f"DEBUG: WebSocket connected for user {user_id_str}. Local active: {len(self.active_connections[user_id_str])}")
        except Exception as e:
            print(f"ERROR: Failed to accept WebSocket for user {user_id}: {e}")
            raise e

    async def disconnect(self, user_id: str, websocket: WebSocket):
        user_id_str = str(user_id)
        if user_id_str in self.active_connections:
            if websocket in self.active_connections[user_id_str]:
                self.active_connections[user_id_str].remove(websocket)
            if not self.active_connections[user_id_str]:
                del self.active_connections[user_id_str]
        print(f"DEBUG: WebSocket disconnected for user {user_id_str}")

    async def notify_user(self, user_id: str, title: str, message: str, type: str = "info"):
        """
        Persists a notification to the database.
        """
        from app.db_raw import get_connection
        async with get_connection() as conn:
            try:
                notif_id = uuid.uuid4()

                now = datetime.now()
                query = """
                    INSERT INTO notifications (notification_id, user_id, title, message, type, is_read, is_active, created_on, updated_on)
                    VALUES (%s::uuid, %s::uuid, %s, %s, %s, FALSE, TRUE, %s, %s)
                    RETURNING *
                """
                notification = await DBWrapper.execute_returning(conn, query, (notif_id, user_id, title, message, type, now, now))
                payload = {
                    "notification_id": str(notif_id),
                    "user_id": str(user_id),
                    "title": title,
                    "message": message,
                    "type": type,
                    "is_read": False,
                    "created_on": now.isoformat()
                }

                # Broadcast directly to local active WebSockets
                await self._notify_local(user_id, payload)
                
                return notification
            except Exception as e:
                print(f"ERROR: Failed to persist notification for user {user_id}: {e}")
                return None

    async def _notify_local(self, user_id: str, payload: dict):
        """Sends notification to WebSockets connected to THIS instance."""
        user_id_str = str(user_id)
        if user_id_str in self.active_connections:
            for connection in self.active_connections[user_id_str]:
                try:
                    await connection.send_text(json.dumps(payload))
                except Exception as e:
                    print(f"DEBUG: Failed to send local notification to {user_id_str}: {e}")


manager = ConnectionManager()

class NotificationService:
    @staticmethod
    async def send_notification(user_id: str, title: str, message: str, type: str = "info"):
        return await manager.notify_user(user_id, title, message, type)
