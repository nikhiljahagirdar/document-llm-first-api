import asyncio
import uuid
import pytest
from app.db_raw import get_connection
from app.services.db.document_db_service import DocumentDBService
from app.services.db.user_db_service import UserDBService
from app.services.db.tenant_db_service import TenantDBService
from app.services.db.notification_db_service import NotificationDBService

@pytest.mark.asyncio
async def test_all_services():
    async with get_connection() as conn:
        # 1. Tenant Service
        tenant_service = TenantDBService()
        tenant_id = uuid.uuid4()
        random_slug = f"test-tenant-{uuid.uuid4().hex[:6]}"
        new_tenant = await tenant_service.create_tenant(conn, {
            "tenant_id": str(tenant_id),
            "name": f"Test Tenant {uuid.uuid4().hex[:4]}",
            "slug": random_slug
        })
        
        # 2. User Service
        user_service = UserDBService()
        
        # Create a FRESH role for this test to avoid FK issues with existing ones
        role_id = uuid.uuid4()
        await user_service.execute(conn, "INSERT INTO roles (role_id, name, tenant_id) VALUES (%s::uuid, %s, %s::uuid)", (role_id, "Test Role", tenant_id))
        
        user_id = uuid.uuid4()
        new_user = await user_service.create_user(
            conn,
            {
                "user_id": str(user_id),
                "tenant_id": str(tenant_id), 
                "email": f"test_{uuid.uuid4().hex[:6]}@example.com", 
                "password_hash": "hash", 
                "role_id": str(role_id), 
                "first_name": "Test", 
                "last_name": "User"
            }
        )
        
        fetched_user = await user_service.get_user_by_id(conn, str(user_id))
        assert fetched_user["email"] == new_user["email"]

        # 3. Document Service
        document_service = DocumentDBService()
        test_doc_id = uuid.uuid4()
        doc = await document_service.create_document(
            conn, test_doc_id, tenant_id, user_id, f"test_{uuid.uuid4().hex[:4]}.pdf", "http://s3/test.pdf", 5000
        )
        await document_service.update_document_statuses(conn, test_doc_id, "processed", "Success", user_id)
        
        # 4. Notification Service
        notif_service = NotificationDBService()
        notif = await notif_service.create_notification(conn, user_id, "Test Title", "Test Body", "info")
        notif_id = notif["notification_id"]
        
        unread = await notif_service.list_notifications(conn, user_id, status="unread")
        assert len(unread) >= 1
        
        await notif_service.mark_as_read(conn, notif_id, user_id)

        # CLEANUP - Correct order for FK constraints
        await conn.execute("DELETE FROM notifications WHERE user_id::uuid = %s::uuid", (user_id,))
        await conn.execute("DELETE FROM document_statuses WHERE document_id::uuid = %s::uuid", (test_doc_id,))
        await conn.execute("DELETE FROM document_history WHERE document_id::uuid = %s::uuid", (test_doc_id,))
        await conn.execute("DELETE FROM documents WHERE document_id::uuid = %s::uuid", (test_doc_id,))
        
        # User dependencies
        await conn.execute("DELETE FROM user_credentials WHERE user_id::uuid = %s::uuid", (user_id,))
        await conn.execute("DELETE FROM audit_logs WHERE user_id::uuid = %s::uuid", (user_id,))
        
        # Now delete user
        await conn.execute("DELETE FROM users WHERE user_id::uuid = %s::uuid", (user_id,))
        
        # Finally delete role and tenant created for THIS test
        await conn.execute("DELETE FROM roles WHERE role_id::uuid = %s::uuid", (role_id,))
        await conn.execute("DELETE FROM tenants WHERE tenant_id::uuid = %s::uuid", (tenant_id,))
