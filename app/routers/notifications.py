from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status, Query
from app.db_raw import get_raw_db
from app.schemas import NotificationResponse
from app.dependencies import get_current_user
from app.services.notification_service import manager
from app.services.db.notification_db_service import NotificationDBService
from typing import List, Optional, Any
import uuid

router = APIRouter(prefix="/notifications", tags=["notifications"])

async def get_notification_service():
    return NotificationDBService()

@router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await manager.connect(user_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(user_id, websocket)

@router.get("", response_model=List[NotificationResponse])
async def get_notifications(
    limit: int = 50,
    offset: int = 0,
    status: str = Query("all", description="Filter by status: all, read, unread"),
    current_user: Any = Depends(get_current_user),
    conn: Any = Depends(get_raw_db),
    service: NotificationDBService = Depends(get_notification_service)
):
    """
    Retrieve notifications for the current user with status filters.
    """
    return await service.list_notifications(conn, current_user.user_id, limit, offset, status)

@router.post("/{notification_id}/read")
async def mark_notification_as_read(
    notification_id: uuid.UUID,
    current_user: Any = Depends(get_current_user),
    conn: Any = Depends(get_raw_db),
    service: NotificationDBService = Depends(get_notification_service)
):
    """
    Mark a specific notification as read.
    """
    updated = await service.mark_as_read(conn, notification_id, current_user.user_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    return {"status": "success"}

@router.post("/read-all")
async def mark_all_notifications_as_read(
    current_user: Any = Depends(get_current_user),
    conn: Any = Depends(get_raw_db),
    service: NotificationDBService = Depends(get_notification_service)
):
    """
    Mark all notifications as read for the current user.
    """
    await service.mark_all_as_read(conn, current_user.user_id)
    return {"status": "success"}

@router.post("/test-notify")
async def create_test_notification(
    current_user: Any = Depends(get_current_user),
    conn: Any = Depends(get_raw_db),
    service: NotificationDBService = Depends(get_notification_service)
):
    """
    Create a test notification for the current user.
    """
    return await service.create_notification(
        conn, 
        current_user.user_id, 
        "Test Notification", 
        "This is a test notification from the API."
    )

@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: uuid.UUID,
    current_user: Any = Depends(get_current_user),
    conn: Any = Depends(get_raw_db),
    service: NotificationDBService = Depends(get_notification_service)
):
    """
    Delete a notification.
    """
    deleted = await service.delete_notification(conn, notification_id, current_user.user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    return {"status": "success"}
