import uuid
from datetime import datetime
from typing import Optional, List, Any
import psycopg
import json
from app.services.db.base_db_service import BaseDBService

class DocumentDBService(BaseDBService):
    async def create_document(
        self,
        conn: psycopg.AsyncConnection,
        doc_id: uuid.UUID,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        filename: str,
        file_url: str,
        file_size: int,
        folder_id: Optional[uuid.UUID] = None,
    ) -> dict:
        now = datetime.now()
        # Task: UPSERT logic to ensure one document per filename per tenant
        query = """
            INSERT INTO documents (
                document_id, tenant_id, user_id, filename, file_url, 
                status, file_size, folder_id, is_active, created_on, updated_on
            )
            VALUES (%s::uuid, %s::uuid, %s::uuid, %s, %s, %s, %s, %s::uuid, TRUE, %s, %s)
            ON CONFLICT (tenant_id, filename) DO UPDATE SET
                user_id = EXCLUDED.user_id,
                file_url = EXCLUDED.file_url,
                status = EXCLUDED.status,
                file_size = EXCLUDED.file_size,
                folder_id = EXCLUDED.folder_id,
                is_active = TRUE,
                updated_on = EXCLUDED.updated_on
            RETURNING *
        """
        doc = await self.execute_returning(
            conn,
            query,
            (
                doc_id,
                tenant_id,
                user_id,
                filename,
                file_url,
                "processing",
                file_size,
                folder_id,
                now,
                now,
            ),
        )
        # Record the initial status in history tables
        await self.update_document_statuses(
            conn, doc["document_id"], "processing", "Uploaded / Re-uploaded", user_id
        )
        return doc

    async def create_manual_document(
        self,
        conn: psycopg.AsyncConnection,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        filename: str,
        content: str,
        folder_id: Optional[uuid.UUID] = None,
        industry_id: Optional[uuid.UUID] = None,
        category_id: Optional[uuid.UUID] = None,
        subcategory_id: Optional[uuid.UUID] = None,
    ) -> dict:
        doc_id = uuid.uuid4()
        now = datetime.now()
        query = """
            INSERT INTO documents (document_id, tenant_id, user_id, filename, file_url, status, file_size, folder_id, industry_id, category_id, subcategory_id, created_on, updated_on)
            VALUES (%s::uuid, %s::uuid, %s::uuid, %s, %s, %s, %s, %s::uuid, %s::uuid, %s::uuid, %s::uuid, %s, %s)
            RETURNING *
        """
        # file_url is empty for manual docs or could be a placeholder
        doc = await self.execute_returning(
            conn,
            query,
            (doc_id, tenant_id, user_id, filename, "", "completed", len(content), folder_id, industry_id, category_id, subcategory_id, now, now),
        )
        
        # Save initial version
        await self.save_document_version(conn, doc_id, 1, content, None, user_id)
        
        await self.update_document_statuses(
            conn, doc_id, "completed", "Created manually", user_id
        )
        return doc

    async def update_document_statuses(
        self,
        conn: psycopg.AsyncConnection,
        document_id: uuid.UUID,
        status: str,
        message: Optional[str] = None,
        user_id: Optional[uuid.UUID] = None,
    ):
        # Update main document status
        await self.execute(
            conn,
            "UPDATE documents SET status = %s, updated_on = %s WHERE document_id::uuid = %s::uuid",
            (status, datetime.now(), document_id),
        )
        # Record status in document_statuses
        await self.execute(
            conn,
            "INSERT INTO document_statuses (status_id, document_id, status, message, status_at) VALUES (%s::uuid, %s::uuid, %s, %s, %s)",
            (uuid.uuid4(), document_id, status, message, datetime.now()),
        )
        # Record history
        if user_id:
            await self.execute(
                conn,
                "INSERT INTO document_history (history_id, document_id, user_id, event_type, status, message) VALUES (%s::uuid, %s::uuid, %s::uuid, %s, %s, %s)",
                (
                    uuid.uuid4(),
                    document_id,
                    user_id,
                    "status_change",
                    status,
                    message or f"Status changed to {status}",
                ),
            )
            
            # Real-time WebSocket update for UI synchronization
            try:
                from app.services.notification_service import NotificationService
                # Use a clear title/type so frontend knows it's a status update
                await NotificationService.send_notification(
                    str(user_id), 
                    f"Document {status.capitalize()}", 
                    message or f"Document is now {status}", 
                    "document_status"
                )
            except Exception as e:
                print(f"DEBUG: Failed to send status notification: {e}")

    async def update_document_metadata(
        self,
        conn: psycopg.AsyncConnection,
        document_id: uuid.UUID,
        file_type: str,
        page_count: int,
        metadata: dict
    ):
        query = """
            UPDATE documents 
            SET file_type = %s, page_count = %s, metadata = %s, updated_on = %s 
            WHERE document_id::uuid = %s::uuid
        """
        await self.execute(
            conn,
            query,
            (file_type, page_count, json.dumps(metadata), datetime.now(), document_id)
        )

    async def get_document(
        self,
        conn: psycopg.AsyncConnection,
        document_id: uuid.UUID,
        tenant_id: uuid.UUID,
        user_id: Optional[uuid.UUID] = None,
        is_admin: bool = False,
    ) -> Optional[dict]:
        query = """
            SELECT 
                d.document_id, d.tenant_id, d.user_id, d.filename, d.file_url, 
                d.status, d.file_size, d.file_type, d.page_count, d.metadata, d.folder_id, d.created_on, d.updated_on,
                d.industry_id, d.category_id, d.subcategory_id, d.google_file_id, d.google_last_modified,
                i.name as industry_name, 
                c.name as category_name, 
                s.name as subcategory_name
            FROM documents d
            LEFT JOIN industries i ON d.industry_id = i.industry_id
            LEFT JOIN categories c ON d.category_id = c.category_id
            LEFT JOIN subcategories s ON d.subcategory_id = s.subcategory_id
            WHERE d.document_id = %s::uuid AND d.tenant_id = %s::uuid
        """
        params = [document_id, tenant_id]
        if not is_admin and user_id:
            query += " AND d.user_id = %s::uuid"
            params.append(user_id)

        return await self.fetch_one(conn, query, tuple(params))

    async def list_documents(
        self,
        conn: psycopg.AsyncConnection,
        tenant_id: uuid.UUID,
        user_id: Optional[uuid.UUID] = None,
        is_admin: bool = False,
        search: Optional[str] = None,
        folder_id: Optional[uuid.UUID] = None,
        limit: int = 20,
        offset: int = 0
    ) -> List[dict]:
        query = """
            SELECT 
                d.document_id, d.tenant_id, d.user_id, d.filename, d.file_url, 
                d.status, d.file_size, d.file_type, d.page_count, d.folder_id, d.created_on, d.updated_on,
                d.industry_id, d.category_id, d.subcategory_id, d.google_file_id, d.google_last_modified,
                i.name as industry_name, 
                c.name as category_name, 
                s.name as subcategory_name
            FROM documents d
            LEFT JOIN industries i ON d.industry_id = i.industry_id
            LEFT JOIN categories c ON d.category_id = c.category_id
            LEFT JOIN subcategories s ON d.subcategory_id = s.subcategory_id
            WHERE d.tenant_id = %s::uuid
        """
        params = [tenant_id]
        if not is_admin and user_id:
            query += " AND d.user_id = %s::uuid"
            params.append(user_id)

        if folder_id:
            query += " AND d.folder_id = %s::uuid"
            params.append(folder_id)
        elif folder_id is None and not search: # root level docs
             # query += " AND d.folder_id IS NULL"
             pass

        if search:
            query += " AND d.filename ILIKE %s"
            params.append(f"%{search}%")

        query += " ORDER BY d.created_on DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        
        return await self.fetch_all(conn, query, tuple(params))

    async def save_document_version(
        self,
        conn: psycopg.AsyncConnection,
        document_id: uuid.UUID,
        version_number: int,
        content: str,
        content_json: Optional[str],
        user_id: uuid.UUID,
        content_html: Optional[str] = None,
        embedding: Optional[List[float]] = None
    ):
        query = """
            INSERT INTO document_versions (version_id, document_id, version_number, content, content_json, content_html, embedding, created_by, created_on)
            VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s, %s::vector, %s::uuid, %s)
        """
        await self.execute(
            conn,
            query,
            (
                uuid.uuid4(),
                document_id,
                version_number,
                content,
                content_json,
                content_html,
                embedding,
                user_id,
                datetime.now(),
            ),
        )

    async def save_document_image(
        self, conn: psycopg.AsyncConnection, document_id: uuid.UUID, image_url: str
    ):
        await self.execute(
            conn,
            "INSERT INTO document_images (image_id, document_id, image_url, created_on) VALUES (%s::uuid, %s::uuid, %s, %s)",
            (uuid.uuid4(), document_id, image_url, datetime.now()),
        )

    async def get_ocr_result(self, conn: psycopg.AsyncConnection, document_id: uuid.UUID) -> Optional[dict]:
        query = "SELECT * FROM ocr_results WHERE document_id::uuid = %s::uuid"
        return await self.fetch_one(conn, query, (document_id,))

    async def get_versions(self, conn: psycopg.AsyncConnection, document_id: uuid.UUID) -> List[dict]:
        query = "SELECT * FROM document_versions WHERE document_id::uuid = %s::uuid ORDER BY version_number DESC"
        return await self.fetch_all(conn, query, (document_id,))

    async def get_document_by_google_id(self, conn: psycopg.AsyncConnection, google_file_id: str, tenant_id: uuid.UUID) -> Optional[dict]:
        query = "SELECT * FROM documents WHERE google_file_id = %s AND tenant_id = %s::uuid AND is_active = TRUE LIMIT 1"
        return await self.fetch_one(conn, query, (google_file_id, tenant_id))

    async def get_images(self, conn: psycopg.AsyncConnection, document_id: uuid.UUID) -> List[dict]:
        query = "SELECT * FROM document_images WHERE document_id::uuid = %s::uuid"
        return await self.fetch_all(conn, query, (document_id,))

    async def delete_document(
        self,
        conn: psycopg.AsyncConnection,
        document_id: uuid.UUID,
        tenant_id: uuid.UUID,
        user_id: Optional[uuid.UUID] = None,
        is_admin: bool = False
    ) -> bool:
        query = "UPDATE documents SET is_active = FALSE, updated_on = %s WHERE document_id = %s::uuid AND tenant_id = %s::uuid"
        params = [datetime.now(), document_id, tenant_id]
        
        if not is_admin and user_id:
            query += " AND user_id = %s::uuid"
            params.append(user_id)
            
        await self.execute(conn, query, tuple(params))
        return True

    async def list_failed_documents(self, conn: psycopg.AsyncConnection) -> List[dict]:
        query = "SELECT * FROM documents WHERE status = 'failed' AND is_active = TRUE AND updated_on < NOW() - INTERVAL '5 minutes' LIMIT 50"
        return await self.fetch_all(conn, query)
