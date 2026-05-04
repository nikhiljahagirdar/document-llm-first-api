from typing import List, Dict
from fastapi import WebSocket
import json
import uuid
import asyncio
from datetime import datetime
from app.db_raw import get_pool, DBWrapper
from app.config import settings
from redis import asyncio as aioredis

class ConnectionManager:
    def __init__(self):
        # Maps user_id to a list of active WebSockets on THIS instance
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self.redis_client = None
        self.pubsub_task = None
        self._redis_lock = asyncio.Lock()
        self._redis_failed_logged = False

    async def _init_redis(self):
        if not settings.USE_REDIS:
            return

        if self.redis_client is None:
            async with self._redis_lock:
                if self.redis_client is not None:
                    return
                try:
                    # Use a shorter timeout for ping to avoid hanging
                    client = aioredis.from_url(
                        settings.REDIS_URL, 
                        decode_responses=True,
                        socket_timeout=5.0,
                        socket_connect_timeout=5.0
                    )
                    await asyncio.wait_for(client.ping(), timeout=5.0)
                    self.redis_client = client
                    
                    # Start pubsub task if not already running
                    if self.pubsub_task is None or self.pubsub_task.done():
                        self.pubsub_task = asyncio.create_task(self._listen_to_redis())
                    
                    print(f"INFO: Notification Redis client initialized (USE_REDIS={settings.USE_REDIS}).")
                    self._redis_failed_logged = False # Reset failure log if successful
                except Exception as e:
                    if not self._redis_failed_logged:
                        print(f"WARNING: Redis not available for notifications (falling back to local): {e}")
                        self._redis_failed_logged = True
                    self.redis_client = None

    async def _listen_to_redis(self):
        """Listens to Redis Pub/Sub for messages to be sent to local WebSockets."""
        while True:
            # Respect USE_REDIS even while running
            if not settings.USE_REDIS:
                await asyncio.sleep(10)
                continue

            try:
                if not self.redis_client:
                    await self._init_redis()
                    if not self.redis_client:
                        await asyncio.sleep(30) # Back off on failure
                        continue

                pubsub = self.redis_client.pubsub()
                async with pubsub as p:
                    await p.subscribe("notifications")
                    print("INFO: Subscribed to Redis 'notifications' channel.")
                    
                    async for message in p.listen():
                        if message["type"] == "message":
                            try:
                                data = json.loads(message["data"])
                                target_user_id = str(data.get("user_id"))
                                payload = data.get("payload")
                                
                                # Send to local connections for this user
                                if target_user_id in self.active_connections:
                                    for connection in self.active_connections[target_user_id]:
                                        try:
                                            await connection.send_text(json.dumps(payload))
                                        except Exception:
                                            pass
                            except Exception as je:
                                print(f"ERROR: Failed to parse Redis message: {je}")
            except Exception as e:
                if settings.USE_REDIS:
                    print(f"WARNING: Redis PubSub connection lost: {e}. Retrying in 30s...")
                self.redis_client = None # Force re-init on next loop
                await asyncio.sleep(30)

    async def connect(self, user_id: str, websocket: WebSocket):
        try:
            await websocket.accept()
            
            if settings.USE_REDIS:
                # Ensure Redis is initialized if enabled
                asyncio.create_task(self._init_redis())
            
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
        Broadcasting and delivery are offloaded to an external cron/Celery job.
        """
        pool = await get_pool()
        async with pool.connection() as conn:
            try:
                notif_id = uuid.uuid4()
                now = datetime.now()
                # We use raw SQL as requested. 
                # The external job will pick up new notifications and broadcast them via Redis/WebSockets.
                query = """
                    INSERT INTO notifications (notification_id, user_id, title, message, type, is_read, is_active, created_on, updated_on)
                    VALUES (%s::uuid, %s::uuid, %s, %s, %s, FALSE, TRUE, %s, %s)
                    RETURNING *
                """
                notification = await DBWrapper.execute_returning(conn, query, (notif_id, user_id, title, message, type, now, now))
                
                # NOTE: Redis publish and local WebSocket broadcast are removed here
                # to offload delivery logic to the external process.
                
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
