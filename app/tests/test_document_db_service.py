import pytest
import uuid
from app.services.db.document_db_service import DocumentDBService
from app.services.db.tenant_db_service import TenantDBService
from app.services.db.user_db_service import UserDBService
from app.db_raw import get_connection

@pytest.mark.asyncio
async def test_document_db_flow():
    async with get_connection() as conn:
        # Create dependencies first
        tenant_service = TenantDBService()
        user_service = UserDBService()
        doc_service = DocumentDBService()
        
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        
        await tenant_service.create_tenant(conn, {
            "tenant_id": str(tenant_id),
            "name": "Doc Test Tenant",
            "slug": f"doc-test-{uuid.uuid4().hex[:6]}"
        })
        
        await user_service.create_user(conn, {
            "user_id": str(user_id),
            "tenant_id": str(tenant_id),
            "email": f"doc_test_{uuid.uuid4().hex[:6]}@example.com",
            "password_hash": "hash",
            "first_name": "Doc",
            "last_name": "Test"
        })
        
        # 1. Create Document
        test_doc_id = uuid.uuid4()
        doc = await doc_service.create_document(
            conn, test_doc_id, tenant_id, user_id, f"test_{uuid.uuid4().hex[:4]}.pdf", "http://s3/test.pdf", 1024
        )
        assert doc["document_id"] == test_doc_id
        
        # 2. Get Document
        fetched_doc = await doc_service.get_document(conn, test_doc_id, tenant_id)
        assert fetched_doc is not None
        
        # 3. Update Status
        await doc_service.update_document_statuses(conn, test_doc_id, "processed", "Test completed", user_id)
            
        # Verify Status
        updated_doc = await doc_service.get_document(conn, test_doc_id, tenant_id)
        assert updated_doc["status"] == "processed"
        
        # CLEANUP
        await conn.execute("DELETE FROM notifications WHERE user_id::uuid = %s::uuid", (user_id,))
        await conn.execute("DELETE FROM document_statuses WHERE document_id::uuid = %s::uuid", (test_doc_id,))
        await conn.execute("DELETE FROM document_history WHERE document_id::uuid = %s::uuid", (test_doc_id,))
        await conn.execute("DELETE FROM documents WHERE document_id::uuid = %s::uuid", (test_doc_id,))
        await conn.execute("DELETE FROM user_credentials WHERE user_id::uuid = %s::uuid", (user_id,))
        await conn.execute("DELETE FROM users WHERE user_id::uuid = %s::uuid", (user_id,))
        await conn.execute("DELETE FROM tenants WHERE tenant_id::uuid = %s::uuid", (tenant_id,))

