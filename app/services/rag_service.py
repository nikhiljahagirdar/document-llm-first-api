import os
import uuid
import asyncio
import logging
import json
from typing import List, Optional, Any

from app.db_raw import DBWrapper, get_connection
from app.config import settings

logger = logging.getLogger(__name__)

class RAGService:

    @staticmethod
    async def ingest_document(conn, document_id: uuid.UUID, tenant_id: uuid.UUID, text: str, version_id: uuid.UUID = None, file_path: str = None):
        """
        Ingests a document into the RAG system using native chunking and pgvector.
        """
        try:
            from app.services.llm_service import LLMService
            from app.services.embedding_service import chunk_text_recursive
            
            logger.info(f"RAG: Starting manual ingestion for doc {document_id}, tenant {tenant_id}")
            
            # 1. Clean up existing chunks for this document
            if conn:
                await DBWrapper.execute(
                    conn,
                    "DELETE FROM document_chunks WHERE document_id = %s::uuid",
                    (document_id,)
                )
            else:
                async with get_connection() as new_conn:
                    await DBWrapper.execute(
                        new_conn,
                        "DELETE FROM document_chunks WHERE document_id = %s::uuid",
                        (document_id,)
                    )
            
            if not text or not text.strip():
                logger.warning(f"RAG: No text provided for document {document_id}")
                return 0

            # 2. Chunk the text
            chunks = chunk_text_recursive(text, chunk_size=1000, chunk_overlap=150)
            if not chunks:
                return 0
                
            # 3. Insert into database (Without Embeddings)
            insert_query = """
                INSERT INTO document_chunks (chunk_id, document_id, version_id, tenant_id, content)
                VALUES (%s::uuid, %s::uuid, %s::uuid, %s::uuid, %s)
            """
            
            async def do_insert(c):
                params_list = [
                    (uuid.uuid4(), document_id, version_id, tenant_id, chunk_text)
                    for chunk_text in chunks
                ]
                await DBWrapper.executemany(c, insert_query, params_list)

            if conn:
                await do_insert(conn)
            else:
                async with get_connection() as new_conn:
                    await do_insert(new_conn)

            # Log usage
            if tenant_id:
                total_len = sum(len(c) for c in chunks)
                LLMService.fire_and_forget_log(tenant_id, "AI Usage (Tokens)", total_len//4)

            logger.info(f"RAG: Successfully ingested {len(chunks)} chunks for document {document_id}")
            return len(chunks)
            
        except Exception as e:
            logger.error(f"RAG: Ingestion failed for {document_id}: {e}", exc_info=True)
            return 0

    @staticmethod
    async def retrieve_context(conn, tenant_id: uuid.UUID, query: str, document_id: Optional[uuid.UUID] = None, limit: int = 5) -> List[str]:
        """
        Retrieves relevant context using PostgreSQL full-text keyword search over the content column.
        """
        try:
            sql = """
                SELECT content::text
                FROM document_chunks 
                WHERE tenant_id::uuid = %s::uuid 
                AND to_tsvector('english', content) @@ websearch_to_tsquery('english', %s)
            """
            params = [tenant_id, query]
            
            if document_id:
                sql += " AND document_id::uuid = %s::uuid"
                params.append(document_id)
                
            sql += " ORDER BY ts_rank(to_tsvector('english', content), websearch_to_tsquery('english', %s)) DESC LIMIT %s"
            params.extend([query, limit])
            
            async def fetch(c):
                return await DBWrapper.fetch_all(c, sql, tuple(params))
                
            if conn:
                results = await fetch(conn)
            else:
                async with get_connection() as new_conn:
                    results = await fetch(new_conn)
            
            # Fallback if no exact full-text matches but document_id is provided
            if not results and document_id:
                fallback_sql = "SELECT content::text FROM document_chunks WHERE tenant_id::uuid = %s::uuid AND document_id::uuid = %s::uuid LIMIT %s"
                if conn:
                    results = await DBWrapper.fetch_all(conn, fallback_sql, (tenant_id, document_id, limit))
                else:
                    async with get_connection() as new_conn:
                        results = await DBWrapper.fetch_all(new_conn, fallback_sql, (tenant_id, document_id, limit))

            return [row["content"] for row in results if row.get("content")]
            
        except Exception as e:
            logger.error(f"RAG: Retrieval failed: {e}")
            return []

    @staticmethod
    async def query_with_rag(conn, query: str, tenant_id: uuid.UUID, document_id: Optional[uuid.UUID] = None, history: List[Any] = None) -> str:
        """
        End-to-end traditional RAG query.
        """
        try:
            logger.info(f"RAG: Querying with traditional RAG Pipeline - Tenant: {tenant_id}, Document: {document_id}, Query: {query}")
            from app.services.llm_service import get_llm, LLMService, _extract_text
            
            # 1. Retrieve Context from document_versions (latest version)
            final_context = ""
            if document_id:
                sql = "SELECT content FROM document_versions WHERE document_id = %s::uuid ORDER BY version_number DESC LIMIT 1"
                row = await DBWrapper.fetch_one(conn, sql, (document_id,))
                if row and row.get("content"):
                    final_context = row["content"]
            
            # Fallback to chunks if no version content or no document_id
            if not final_context:
                chunks = await RAGService.retrieve_context(conn, tenant_id, query, document_id, limit=10)
                if chunks:
                    final_context = "\n\n".join([f"--- Chunk {i+1} ---\n{c}" for i, c in enumerate(chunks)])

            if not final_context:
                return "No relevant information found in your documents to answer this question."

            # 2. Build History string
            history_str = ""
            if history:
                history_parts = []
                for msg in history:
                    role = "User" if (getattr(msg, 'role', 'user') == 'user') else "Assistant"
                    content = getattr(msg, 'content', '')
                    history_parts.append(f"{role}: {content}")
                history_str = "\n".join(history_parts)

            # 3. Build Prompt
            formatted_prompt = f"""
            You are a professional Document Intelligence Assistant. 
            Answer the question based ONLY on the provided context documents. 

            ### UI REPRESENTATION GUIDELINES:
            1. **Clarity**: Use clear, concise language.
            2. **Structure**: If the answer involves data, use an HTML table (standard <table> tags with <thead> and <tbody>).
            3. **Visuals**: If the answer involves trends, comparisons, or distributions, include a JSON block marked as `### DATA_FOR_CHART ###` containing keys: `type` (bar, pie, line), `labels` (array), and `datasets` (array of {{label, data}}).
            4. **Rich Text**: Use standard HTML for bolding, lists, and headings for better readability in the UI. Do NOT include <html> or <body> tags.

            Context Documents:
            {final_context[:100000]}

            ### CHAT HISTORY:
            {history_str}

            Question: {query}
            Answer:
            """
            
            # 4. Generate Answer
            llm = get_llm(temperature=0.3)
            response = await llm.ainvoke(formatted_prompt)
            
            if tenant_id:
                await LLMService.log_response_usage(conn, tenant_id, response, input_text=formatted_prompt)
                
            return _extract_text(response.content)

        except Exception as e:
            logger.error(f"RAG: Query failed: {e}", exc_info=True)
            return f"Error: {e}"

    @staticmethod
    async def query_with_agent(conn, query: str, tenant_id: uuid.UUID, history: List[Any] = None) -> str:
        """
        Agentic RAG orchestrator that:
        1. Analyzes the user's intent.
        2. Decomposes the request into multiple optimized search queries.
        3. Retrieves and aggregates context in parallel.
        4. Synthesizes a comprehensive final answer.
        """
        try:
            logger.info(f"RAG AGENT: Starting agentic query for tenant {tenant_id}: {query}")
            from app.services.llm_service import get_llm, LLMService, _extract_text
            import json

            # 0. Build History string
            history_str = ""
            if history:
                history_parts = []
                for msg in history:
                    role = "User" if (getattr(msg, 'role', 'user') == 'user') else "Assistant"
                    content = getattr(msg, 'content', '')
                    history_parts.append(f"{role}: {content}")
                history_str = "\n".join(history_parts)
            
            # Step 1: Query Decomposition & Planning
            plan_prompt = f"""
            You are an expert Document Search Agent.
            Analyze the user's question and break it down into up to 3 distinct, highly targeted search queries to search a vector database.
            
            ### CHAT HISTORY:
            {history_str}

            User Question: {query}
            
            Return ONLY a JSON array of strings representing the search queries. Example: ["query 1", "query 2"]
            """
            
            llm_plan = get_llm(temperature=0.1).bind(response_mime_type="application/json")
            plan_response = await llm_plan.ainvoke(plan_prompt)
            
            if tenant_id:
                # Log usage for the planning stage
                await LLMService.log_response_usage(conn, tenant_id, plan_response, input_text=plan_prompt)

            # Extract generated queries safely
            text = _extract_text(plan_response.content).strip()
            if text.startswith('```'):
                text = text.split('\n', 1)[-1]
                if text.endswith('```'):
                    text = text.rsplit('```', 1)[0]
            
            try:
                search_queries = json.loads(text.strip())
                if not isinstance(search_queries, list):
                    search_queries = [query]
            except Exception:
                search_queries = [query]
                
            # Deduplicate and limit to 3 queries to manage latency
            search_queries = list(dict.fromkeys([str(q) for q in search_queries]))[:3]
            logger.info(f"RAG AGENT: Generated optimized search queries: {search_queries}")
            
            # Step 2: Parallel Retrieval
            all_chunks = set()
            
            retrieve_tasks = [
                RAGService.retrieve_context(None, tenant_id, sq, limit=4)
                for sq in search_queries
            ]
            results = await asyncio.gather(*retrieve_tasks, return_exceptions=True)
            
            for res in results:
                if isinstance(res, list):
                    all_chunks.update(res)
                    
            context_parts = []
            if all_chunks:
                context_parts.append("### Retrieved Document Context:\n" + "\n\n----- \n\n".join(all_chunks))
                
            if not context_parts:
                logger.warning("RAG AGENT: No context found during agentic retrieval.")
                return "No relevant information found in your documents to answer this question."
                
            final_context = "\n\n".join(context_parts)
            logger.info(f"RAG AGENT: Final aggregated context length: {len(final_context)}")
            
            # Step 3: Final Answer Synthesis
            synthesis_prompt = f"""
            You are a professional Document Intelligence Agent.
            Answer the user's question thoroughly based ONLY on the provided context retrieved from multiple searches across their documents.
            Synthesize the information logically. If the context does not contain the answer, state that clearly.
            
            ### UI REPRESENTATION GUIDELINES:
            1. **Clarity**: Use clear, concise language.
            2. **Structure**: If the answer involves data, use an HTML table (standard <table> tags with <thead> and <tbody>).
            3. **Visuals**: If the answer involves trends, comparisons, or distributions, include a JSON block marked as `### DATA_FOR_CHART ###` containing keys: `type` (bar, pie, line), `labels` (array), and `datasets` (array of {{label, data}}).
            4. **Rich Text**: Use standard HTML for bolding, lists, and headings for better readability in the UI. Do NOT include <html> or <body> tags.
            
            Context:
            {final_context[:100000]}
            
            ### CHAT HISTORY:
            {history_str}

            Question: {query}
            
            Answer:
            """
            
            llm_synth = get_llm(temperature=0.3)
            final_response = await llm_synth.ainvoke(synthesis_prompt)
            
            if tenant_id:
                await LLMService.log_response_usage(conn, tenant_id, final_response, input_text=synthesis_prompt)
                
            return _extract_text(final_response.content)

        except Exception as e:
            logger.error(f"RAG AGENT: Query failed: {e}", exc_info=True)
            return f"Error executing agent query: {e}"
