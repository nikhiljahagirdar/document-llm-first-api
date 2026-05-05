import os
import uuid
import asyncio
import logging
import json
from typing import List, Optional, Any

from haystack import Pipeline, Document, component
from haystack.components.writers import DocumentWriter
from haystack.document_stores.types import DuplicatePolicy
from haystack.components.builders.prompt_builder import PromptBuilder

from app.db_raw import DBWrapper, DATABASE_URL, get_connection
from app.services.llm_service import LLMService, GeminiTextEmbedder, GeminiGenerator, GeminiDocumentEmbedder
from app.services.custom_haystack import CustomPgvectorDocumentStore
from app.config import settings

logger = logging.getLogger(__name__)

@component
class RobustDoclingConverter:
    """Custom Haystack component using our configured Docling converter."""
    @component.output_types(documents=List[Document])
    def run(self, sources: List[str]):
        from app.services.document_processing import get_docling_converter
        import gc
        converter = get_docling_converter()
        documents = []
        for source in sources:
            try:
                logger.info(f"RobustDoclingConverter: Converting {source}")
                result = converter.convert(source)
                doc = result.document
                markdown_text = doc.export_to_markdown()
                documents.append(Document(content=markdown_text, meta={"file_path": source}))
            except Exception as e:
                logger.error(f"RobustDoclingConverter failed for {source}: {e}")
            finally:
                gc.collect()
        return {"documents": documents}

@component
class MetadataEnricher:
    """Haystack component to add metadata to documents before indexing."""
    def __init__(self, metadata: dict):
        self.metadata = metadata

    @component.output_types(documents=List[Document])
    def run(self, documents: List[Document]):
        for doc in documents:
            doc.meta.update(self.metadata)
            # Ensure chunk_id is a valid UUID for pgvector
            if not doc.id or doc.id == doc.content: # Default Haystack ID can be content hash
                import hashlib
                content_hash = hashlib.md5(doc.content.encode()).hexdigest()
                doc.id = str(uuid.UUID(content_hash))
        return {"documents": documents}

class RAGService:

    @staticmethod
    def get_document_store():
        """Initializes and returns the Haystack Document Store."""
        from haystack.utils import Secret
        return CustomPgvectorDocumentStore(
            connection_string=Secret.from_token(DATABASE_URL),
            table_name="document_chunks",
            embedding_dimension=3072, # Matches database schema (gemini-embedding-2)
            vector_function="cosine_similarity",
            recreate_table=False,
        )

    @staticmethod
    async def ingest_document(conn, document_id: uuid.UUID, tenant_id: uuid.UUID, text: str, version_id: uuid.UUID = None, file_path: str = None):
        """
        Ingests a document into the RAG system using a Robust Docling pipeline.
        """
        try:
            document_store = RAGService.get_document_store()
            
            # 1. Clean up existing chunks for this document
            if conn:
                await DBWrapper.execute(
                    conn,
                    "DELETE FROM document_chunks WHERE document_id = %s::uuid",
                    (document_id,)
                )
            
            # 2. Build and run indexing pipeline
            from haystack.components.preprocessors import DocumentSplitter
            pipeline = Pipeline()
            
            metadata = {
                "document_id": str(document_id),
                "tenant_id": str(tenant_id),
                "version_id": str(version_id) if version_id else None
            }
            logger.info(f"RAG: Starting ingestion for doc {document_id}, tenant {tenant_id}")

            pipeline.add_component("splitter", DocumentSplitter(split_by="word", split_length=500, split_overlap=50))
            pipeline.add_component("enricher", MetadataEnricher(metadata=metadata))
            pipeline.add_component("embedder", GeminiDocumentEmbedder())
            pipeline.add_component("writer", DocumentWriter(document_store=document_store, policy=DuplicatePolicy.OVERWRITE))
            
            pipeline.connect("splitter", "enricher")
            pipeline.connect("enricher", "embedder")
            pipeline.connect("embedder", "writer")

            if file_path and os.path.exists(file_path):
                # Use our robust converter
                pipeline.add_component("converter", RobustDoclingConverter())
                pipeline.connect("converter", "splitter")
                
                # Run indexing
                result = await asyncio.to_thread(pipeline.run, {"converter": {"sources": [file_path]}})
                logger.info(f"RAG: Pipeline run complete for {document_id}. Result: {result}")
            else:
                # Fallback to simple text ingestion
                doc = Document(content=text, meta=metadata)
                result = await asyncio.to_thread(pipeline.run, {"splitter": {"documents": [doc]}})
                logger.info(f"RAG: Simple ingestion complete for {document_id}. Result: {result}")

            logger.info(f"RAG: Ingested document {document_id} for tenant {tenant_id}")
            return 1
        except Exception as e:
            logger.error(f"RAG: Ingestion failed for {document_id}: {e}", exc_info=True)
            return 0

    @staticmethod
    async def retrieve_context(conn, tenant_id: uuid.UUID, query: str, document_id: Optional[uuid.UUID] = None, limit: int = 5) -> List[str]:
        """
        Retrieves relevant context using a semantic search via Haystack.
        """
        try:
            document_store = RAGService.get_document_store()
            from haystack_integrations.components.retrievers.pgvector import PgvectorEmbeddingRetriever
            
            filters = {"tenant_id": str(tenant_id)}
            if document_id:
                filters["document_id"] = str(document_id)

            # Build Query Pipeline
            pipeline = Pipeline()
            pipeline.add_component("text_embedder", GeminiTextEmbedder())
            pipeline.add_component("retriever", PgvectorEmbeddingRetriever(document_store=document_store))
            
            pipeline.connect("text_embedder.embedding", "retriever.query_embedding")
            
            # Run retrieval
            result = await asyncio.to_thread(
                pipeline.run, 
                {
                    "text_embedder": {"text": query},
                    "retriever": {"top_k": limit, "filters": filters}
                }
            )
            
            docs = result.get("retriever", {}).get("documents", [])
            return [doc.content for doc in docs]
        except Exception as e:
            logger.error(f"RAG: Retrieval failed: {e}")
            return []

    @staticmethod
    async def query_with_rag(conn, query: str, tenant_id: uuid.UUID, document_id: Optional[uuid.UUID] = None) -> str:
        """
        End-to-end RAG query using Haystack pipeline.
        With fallback to full document text and structured data from document_versions if specific document is targeted.
        """
        try:
            logger.info(f"RAG: Querying with RAG - Tenant: {tenant_id}, Document: {document_id}, Query: {query}")
            
            # 1. Retrieve Context via Semantic Search (RAG)
            chunks = await RAGService.retrieve_context(conn, tenant_id, query, document_id)
            
            context_parts = []
            if chunks:
                context_parts.append("### Relevant Document Sections:\n" + "\n\n----- \n\n".join(chunks))
                logger.info(f"RAG: Found {len(chunks)} semantic chunks.")

            # 2. Fallback / Enrichment for Single Document Chat
            if document_id:
                logger.info(f"RAG: Fetching full context from document_versions for document {document_id}")
                from app.services.db.document_db_service import DocumentDBService
                doc_service = DocumentDBService()
                
                versions = []
                if conn:
                    versions = await doc_service.get_versions(conn, document_id)
                else:
                    async with get_connection() as new_conn:
                        versions = await doc_service.get_versions(new_conn, document_id)
                
                if versions:
                    v = versions[0]
                    full_text = v.get("content")
                    content_json = v.get("content_json")
                    
                    if full_text:
                        # If RAG found nothing or if it's a specific document chat, use full text
                        if not chunks or len(full_text) < 150000:
                            context_parts.append(f"### Full Document Text:\n{full_text}")
                            logger.info(f"RAG: Included full text (Length: {len(full_text)})")
                    
                    if content_json:
                        # Include structured data if available, as it often has better relationship info
                        json_str = json.dumps(content_json, indent=2) if isinstance(content_json, (dict, list)) else str(content_json)
                        if len(json_str) < 50000: # Don't overwhelm if JSON is huge
                            context_parts.append(f"### Extracted Structured Data (JSON):\n{json_str}")
                            logger.info(f"RAG: Included structured data (Length: {len(json_str)})")
                else:
                    logger.warning(f"RAG: No versions found for document {document_id}")
            
            if not context_parts:
                logger.warning("RAG: No context found after RAG and enrichment.")
                return "No relevant information found in your documents. Please ensure the document has been processed successfully and contains extractable text."

            final_context = "\n\n".join(context_parts)
            logger.info(f"RAG: Final context length for LLM: {len(final_context)}")

            # 3. Generate Answer
            prompt_template = """
            You are a professional Document Intelligence Assistant. 
            Answer the question based ONLY on the provided context. 
            The context may include semantic chunks, full document text, and extracted structured data (JSON).

            ### UI REPRESENTATION GUIDELINES:
            1. **Clarity**: Use clear, concise language.
            2. **Structure**: If the answer involves data, use an HTML table (standard <table> tags with <thead> and <tbody>).
            3. **Visuals**: If the answer involves trends, comparisons, or distributions, include a JSON block marked as `### DATA_FOR_CHART ###` containing keys: `type` (bar, pie, line), `labels` (array), and `datasets` (array of {label, data}).
            4. **Rich Text**: Use standard HTML for bolding, lists, and headings for better readability in the UI. Do NOT include <html> or <body> tags.

            Context:
            {{context}}

            Question: {{query}}

            Answer:
            """
            
            pipeline = Pipeline()
            pipeline.add_component("prompt_builder", PromptBuilder(template=prompt_template))
            pipeline.add_component("llm", GeminiGenerator())
            pipeline.connect("prompt_builder", "llm")
            
            result = await asyncio.to_thread(
                pipeline.run,
                {
                    "prompt_builder": {"context": final_context, "query": query},
                    "llm": {"tenant_id": tenant_id}
                }
            )
            
            replies = result.get("llm", {}).get("replies", [])
            response = replies[0] if replies else "Failed to generate an answer."
            logger.info(f"RAG: LLM response generated (Length: {len(response)})")
            return response

        except Exception as e:
            logger.error(f"RAG: Query failed: {e}", exc_info=True)
            return f"Error: {e}"
