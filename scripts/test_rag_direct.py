import asyncio
import sys
import os
import selectors
import uuid
import logging

# Add root directory to path to import app modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

from app.db_raw import get_connection
from app.services.rag_service import RAGService

async def test_rag():
    # Use IDs found in the database
    doc_id = uuid.UUID("77c1667c-71ef-4181-8a86-0363befae5fa")
    tenant_id = uuid.UUID("9417b2e0-10cc-4624-a333-0b0191b56dc3")
    query = "What is the total balance in this statement?"
    
    print(f"Testing RAG for Doc: {doc_id}, Tenant: {tenant_id}")
    async with get_connection() as conn:
        response = await RAGService.query_with_rag(conn, query, tenant_id, doc_id)
        print("\nAI RESPONSE:")
        print(response)

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(test_rag())