import asyncio
import uuid
import sys
import os
import psycopg
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

async def seed_sample_doc():
    # Use direct connection instead of pool to avoid Proactor/Pool issues on Windows
    async with await psycopg.AsyncConnection.connect(DATABASE_URL) as conn:
        async with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            print("Connected to DB...")
            # Get demo tenant
            await cur.execute("SELECT tenant_id FROM tenants WHERE slug = 'demo-tenant'")
            tenant = await cur.fetchone()
            if not tenant:
                print("Demo tenant not found. Please run scripts/seed_data.py first.")
                return
            
            tenant_id = tenant["tenant_id"]
            
            # Get a subcategory
            await cur.execute("SELECT subcategory_id FROM subcategories LIMIT 1")
            sub = await cur.fetchone()
            subcategory_id = sub["subcategory_id"] if sub else None
            
            # Get a user from the tenant
            await cur.execute("SELECT user_id FROM users WHERE tenant_id = %s LIMIT 1", (tenant_id,))
            user = await cur.fetchone()
            user_id = user["user_id"] if user else None

            doc_id = uuid.uuid4()
            now = datetime.now()
            
            # Insert document
            await cur.execute("""
                INSERT INTO documents (document_id, tenant_id, user_id, filename, file_url, subcategory_id, status, created_on, updated_on)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (doc_id, tenant_id, user_id, "Sample_Service_Agreement.pdf", "https://example.com/sample.pdf", subcategory_id, "processed", now, now))
            
            # Insert version with content
            version_id = uuid.uuid4()
            content = """
            # SERVICE AGREEMENT
            
            This Service Agreement ("Agreement") is made as of May 5, 2026, by and between:
            
            **Provider**: TechFlow Solutions Inc.
            **Client**: Global Industries Corp.
            
            ### 1. Services Provided
            The Provider agrees to provide cloud infrastructure management and AI integration services.
            
            ### 2. Fees and Payment
            The Client shall pay the Provider a monthly fee of $5,000 USD. 
            Payments are due on the 1st of each month.
            A late fee of 5% will be applied to payments delayed by more than 10 days.
            
            ### 3. Term and Termination
            This Agreement shall remain in effect for 12 months.
            Either party may terminate with 30 days written notice.
            
            ### 4. Confidentiality
            Both parties agree to keep all business information confidential.
            """
            
            await cur.execute("""
                INSERT INTO document_versions (version_id, document_id, version_number, content, created_on)
                VALUES (%s, %s, %s, %s, %s)
            """, (version_id, doc_id, 1, content, now))
            
            await conn.commit()
            print(f"Sample document seeded successfully!")
            print(f"DOC_ID: {doc_id}")
            print(f"TENANT_ID: {tenant_id}")

if __name__ == "__main__":
    import selectors
    loop_factory = lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()) if sys.platform == 'win32' else None
    if loop_factory:
        asyncio.run(seed_sample_doc(), loop_factory=loop_factory)
    else:
        asyncio.run(seed_sample_doc())
