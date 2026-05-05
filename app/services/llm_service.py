import os
import json
import uuid
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from app.config import settings

logger = logging.getLogger(__name__)

# Initialize the Gemini GenAI Client lazily
_client = None

def get_genai_client():
    global _client
    if _client is None:
        from google import genai
        api_key = settings.GEMINI_API_KEY
        if not api_key:
            # Fallback to env just in case settings isn't populated
            api_key = os.getenv("GEMINI_API_KEY")
        
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set in settings or environment")
            
        _client = genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})
        print("INFO: GenAI Client initialized with Gemini API Key (v1beta)")
    return _client

try:
    from haystack import component, Document
except ImportError:
    class Document:
        def __init__(self, content, meta=None, id=None, embedding=None):
            self.content = content
            self.meta = meta or {}
            self.id = id
            self.embedding = embedding

    def component(cls):
        return cls
    def mock_output_types(**kwargs):
        def decorator(func):
            return func
        return decorator
    component.output_types = mock_output_types

@component
class GeminiTextEmbedder:
    """Haystack component for Gemini embeddings."""
    def __init__(self, model: str = None):
        self.model = model or settings.AI_EMBEDDING_MODEL

    @component.output_types(embedding=List[float])
    def run(self, text: str, tenant_id: Optional[Any] = None, user_id: Optional[Any] = None, conn: Optional[Any] = None):
        from google.genai import types
        try:
            client = get_genai_client()
            
            # Ensure model name is correct (prefix with models/ if missing)
            model_name = self.model
            if not model_name.startswith("models/"):
                model_name = f"models/{model_name}"

            # Use SYNC call
            response = client.models.embed_content(
                model=model_name,
                contents=text,
                config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY")
            )
            
            if not response.embeddings:
                raise ValueError("No embeddings returned from Gemini API")
                
            emb = response.embeddings[0].values
            
            # Log usage (fire and forget)
            if tenant_id:
                LLMService.fire_and_forget_log(tenant_id, "AI Usage (Tokens)", len(text)//4, user_id=user_id, input_text=text)
            
            return {"embedding": emb}
        except Exception as e:
            logger.error(f"GeminiTextEmbedder error: {e}")
            if "LIMIT REACHED" in str(e): raise e
            # Default to 3072 dimensions to match database schema (gemini-embedding-2)
            return {"embedding": [0.0] * 3072}

@component
class GeminiDocumentEmbedder:
    """Haystack component for batch Gemini embeddings of Documents."""
    def __init__(self, model: str = None):
        self.model = model or settings.AI_EMBEDDING_MODEL

    @component.output_types(documents=List[Document])
    def run(self, documents: List[Document], tenant_id: Optional[Any] = None, user_id: Optional[Any] = None):
        from google.genai import types
        print(f"DEBUG: GeminiDocumentEmbedder received {len(documents)} documents")
        try:
            client = get_genai_client()
            model_name = self.model
            if not model_name.startswith("models/"):
                model_name = f"models/{model_name}"

            texts = [doc.content for doc in documents]
            if not texts:
                print("DEBUG: GeminiDocumentEmbedder texts is empty")
                return {"documents": documents}

            # Use Batch Embed
            response = client.models.embed_content(
                model=model_name,
                contents=texts,
                config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT")
            )
            
            for i, doc in enumerate(documents):
                doc.embedding = response.embeddings[i].values
            
            # Log usage (fire and forget)
            if tenant_id:
                total_len = sum(len(t) for t in texts)
                LLMService.fire_and_forget_log(tenant_id, "AI Usage (Tokens)", total_len//4, user_id=user_id)
            
            return {"documents": documents}
        except Exception as e:
            logger.error(f"GeminiDocumentEmbedder error: {e}")
            if "LIMIT REACHED" in str(e): raise e
            # Fallback to zero embeddings
            for doc in documents:
                doc.embedding = [0.0] * 3072
            return {"documents": documents}

@component
class GeminiGenerator:
    """Haystack component for Gemini text generation."""
    @component.output_types(replies=List[str])
    def run(self, prompt: str, tenant_id: Optional[Any] = None, user_id: Optional[Any] = None, conn: Optional[Any] = None):
        from app.services.embedding_service import get_genai_client
        try:
            client = get_genai_client()
            model_name = settings.AI_LLM_MODEL
            
            # Use SYNC call
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
            )
            
            # Log usage (fire and forget)
            if tenant_id:
                usage = response.usage_metadata
                if usage and usage.total_token_count:
                    LLMService.fire_and_forget_log(
                        tenant_id, 
                        "AI Usage (Tokens)", 
                        usage.total_token_count, 
                        user_id=user_id,
                        input_text=prompt,
                        output_text=response.text
                    )
                 
            return {"replies": [response.text]}
        except Exception as e:
            logger.error(f"GeminiGenerator error: {e}")
            if "LIMIT REACHED" in str(e): raise e
            return {"replies": [f"Error generating answer: {e}"]}

class LLMService:
    @staticmethod
    def fire_and_forget_log(tenant_id, metric, quantity, user_id=None, input_text=None, output_text=None):
        """Helper to log usage without blocking, handling both sync and async environments."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(LLMService.log_llm_usage(
                None, tenant_id, metric, quantity, user_id, input_text, output_text
            ))
        except RuntimeError:
            # No event loop, we can't easily log async here without blocking or starting a loop
            # For sync context like Haystack 'run', we'll just try a sync insert if DATABASE_URL is available
            from app.db_raw import DATABASE_URL
            import psycopg
            if DATABASE_URL:
                try:
                    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
                        now = datetime.now()
                        log_id = str(uuid.uuid4())
                        sql = """
                            INSERT INTO usage_logs 
                            (log_id, tenant_id, user_id, metric_name, quantity, input_text, output_text, created_on, updated_on) 
                            VALUES (%s::uuid, %s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s)
                        """
                        with conn.cursor() as cur:
                            cur.execute(sql, (log_id, str(tenant_id), str(user_id) if user_id else None, metric, quantity, input_text, output_text, now, now))
                except Exception as e:
                    logger.debug(f"Sync usage logging failed: {e}")

    @staticmethod
    async def generate_template_ai(
        industry: Optional[str], 
        category: Optional[str], 
        subcategory: Optional[str], 
        tenant_id: Any, 
        conn: Any = None, 
        override_prompt: Optional[str] = None,
        user_prompt: Optional[str] = None,
        user_id: Any = None
    ) -> Dict[str, Any]:
        """
        AI-powered template builder. Generates a logical structure and HTML layout based on classification or generic prompt.
        """
        from google.genai import types
        from app.services.db.metering_db_service import MeteringDBService
        
        # Check Limits
        if conn and tenant_id:
            await MeteringDBService().check_usage_limits(conn, uuid.UUID(str(tenant_id)), "ai")

        system_instruction = f"""
        {settings.AI_SYSTEM_PROMPT}
        You are an expert Document Template Architect. 
        Your task is to design a high-quality, professional document template.
        """

        if user_prompt and not (industry or category or subcategory):
            prompt = f"""
            Task: Create a professional document template based on the following user request:
            ---
            {user_prompt}
            ---

            ### REQUIREMENTS:
            1. SCHEMA: Identify all logical fields (keys and types) for this document.
            2. HTML: Create a clean, professional HTML structure using modern CSS (inline). Use {{field_name}} placeholders. Do NOT include <html>, <head>, or <body> tags. The output must be safe to embed directly into a React component (e.g. use a wrapper <div>).
            3. OUTPUT: You MUST return a JSON object with:
               "template_name": "Professional Name",
               "description": "Brief description",
               "template_schema": {{"field_1": "type", "field_2": "type"}},
               "html_content": "<div>...</div>",
               "document_type": "invoice|contract|report|other"

            Return ONLY the JSON.
            """
        elif override_prompt:
            prompt = f"""
            {override_prompt}
            
            Context:
            Industry: {industry}
            Category: {category}
            Subcategory: {subcategory}
            
            Return ONLY a JSON object with:
            "template_name": "Professional Name",
            "description": "Brief description",
            "template_schema": {{"field_1": "type", "field_2": "type"}},
            "html_content": "<div>...</div>",
            "document_type": "invoice|contract|report|other"
            
            Note: Do NOT include <html>, <head>, or <body> tags in html_content. Use a wrapper <div> instead.
            """
        else:
            prompt = f"""
            Create a document template for:
            Industry: {industry}
            Category: {category}
            Subcategory: {subcategory}

            ### REQUIREMENTS:
            1. SCHEMA: Identify all standard fields expected in such a document.
            2. HTML: Create a clean, professional HTML structure using modern CSS (inline). Use {{field_name}} placeholders. Do NOT include <html>, <head>, or <body> tags. The output must be safe to embed directly into a React component (e.g. use a wrapper <div>).
            3. OUTPUT: You MUST return a JSON object with:
               "template_name": "Professional Name",
               "description": "Brief description",
               "template_schema": {{"field_1": "type", "field_2": "type"}},
               "html_content": "<div>...</div>",
               "document_type": "invoice|contract|report|other"

            Return ONLY the JSON.
            """

        try:
            client = get_genai_client()
            response = await client.aio.models.generate_content(
                model=settings.AI_LLM_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    temperature=0.7,
                ),
            )

            await LLMService.log_response_usage(conn, tenant_id, response, user_id=user_id, input_text=prompt)
            text = response.text.strip()
            if text.startswith('```'):
                lines = text.split('\n')
                if lines[0].startswith('```'):
                    lines = lines[1:]
                if lines[-1].startswith('```'):
                    lines = lines[:-1]
                text = '\n'.join(lines).strip()
            return json.loads(text)
        except Exception as e:
            logger.error(f"AI Template Generation failed: {e}")
            if "LIMIT REACHED" in str(e): raise e
            return {"error": str(e)}

    @staticmethod
    async def log_response_usage(conn: Any, tenant_id: Any, response: Any, user_id: Any = None, input_text: Any = None):
        """Extracts and logs token usage from a Gemini response."""
        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            usage = response.usage_metadata
            try:
                # Log total tokens as "AI Usage (Tokens)"
                if usage.total_token_count:
                    await LLMService.log_llm_usage(
                        conn, 
                        tenant_id, 
                        "AI Usage (Tokens)", 
                        usage.total_token_count, 
                        user_id=user_id,
                        input_text=input_text,
                        output_text=response.text if hasattr(response, 'text') else None
                    )
                
                # Internal prompt tokens for debugging
                if usage.prompt_token_count:
                    await LLMService.log_llm_usage(conn, tenant_id, "prompt_tokens", usage.prompt_token_count, user_id=user_id)
            except Exception as e:
                logger.debug(f"Failed to log detailed usage: {e}")

    @staticmethod
    async def log_llm_usage(
        conn: Any,
        tenant_id: Any,
        metric: str = "AI Usage (Tokens)",
        quantity: int = 1,
        user_id: Any = None,
        input_text: Optional[str] = None,
        output_text: Optional[str] = None
    ):
        """Internal helper to log AI usage (Async) using raw SQL."""
        now = datetime.now()
        try:
            from app.db_raw import DBWrapper, pool, get_pool
            tid_str = str(tenant_id)
            uid_str = str(user_id) if user_id else None
            log_id = str(uuid.uuid4())
            
            sql = """
                INSERT INTO usage_logs 
                (log_id, tenant_id, user_id, metric_name, quantity, input_text, output_text, created_on, updated_on) 
                VALUES (%s::uuid, %s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s)
            """
            params = (log_id, tid_str, uid_str, metric, quantity, input_text, output_text, now, now)

            if conn is None:
                p = await get_pool()
                async with p.connection() as new_conn:
                    await DBWrapper.execute(new_conn, sql, params)
            elif hasattr(conn, 'cursor') and not hasattr(conn, '__aenter__'):
                # Sync connection (psycopg3)
                with conn.cursor() as cur:
                    cur.execute(sql, params)
            else:
                # Assume async connection
                await DBWrapper.execute(conn, sql, params)
        except Exception as e:
            logger.debug(f"Failed to log usage: {e}")

    @staticmethod
    async def detect_industry(
        text: str, industries_or_subcategories: List[Any], tenant_id: Any, conn: Any = None, user_id: Any = None
    ) -> Dict[str, Any]:
        """
        Use AI to automatically detect the industry, category, and subcategory of a document.
        Can handle either a hierarchical industry list or a flat list of subcategories.
        """
        from google.genai import types
        from app.services.db.metering_db_service import MeteringDBService
        
        # Check Limits
        if conn and tenant_id:
            await MeteringDBService().check_usage_limits(conn, uuid.UUID(str(tenant_id)), "ai")

        if not text.strip() or not industries_or_subcategories:
            return {
                "industry_id": None, "category_id": None, "subcategory_id": None, "confidence": 0.0,
            }

        # Check if we have a flat list of subcategories (requested by user for better precision)
        if industries_or_subcategories and "subcategory_id" in industries_or_subcategories[0]:
            print(f"DEBUG: Using flat subcategory list, size: {len(industries_or_subcategories)}")
            classification_list = [
                {
                    "industry_id": str(x.get("industry_id")),
                    "industry_name": x.get("industry_name"),
                    "category_id": str(x.get("category_id")),
                    "category_name": x.get("category_name"),
                    "subcategory_id": str(x.get("subcategory_id")),
                    "subcategory_name": x.get("subcategory_name")
                }
                for x in industries_or_subcategories
            ]
        else:
            print(f"DEBUG: Using hierarchical industry list, size: {len(industries_or_subcategories)}")
            classification_list = [
                {
                    "id": str(i.get("industry_id")),
                    "name": i.get("name"),
                    "categories": [
                        {
                            "id": str(c.get("category_id")),
                            "name": c.get("name"),
                            "subcategories": [
                                {"id": str(s.get("subcategory_id")), "name": s.get("name")}
                                for s in (c.get("subcategories") or [])
                            ],
                        }
                        for c in (i.get("categories") or [])
                    ],
                }
                for i in industries_or_subcategories
            ]

        prompt = f"""
        You are a document classification assistant. 
        Your task is to analyze the document text and map it to the MOST RELEVANT Industry, Category, and Subcategory from the provided list.

        ### AVAILABLE CLASSIFICATIONS:
        {json.dumps(classification_list, indent=2)}

        ### DOCUMENT TEXT (truncated):
        {text[:8000]}

        ### OUTPUT REQUIREMENTS:
        Return ONLY a JSON object with the following fields:
        - industry_id: UUID string
        - industry_name: string
        - category_id: UUID string
        - category_name: string
        - subcategory_id: UUID string
        - subcategory_name: string
        - confidence: float (0.0 to 1.0)
        """

        try:
            client = get_genai_client()
            response = await client.aio.models.generate_content(
                model=settings.AI_LLM_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction="You are an expert at document classification. Only return valid JSON.",
                    response_mime_type="application/json",
                    temperature=0.1, # Low temperature for more deterministic results
                ),
            )
            await LLMService.log_response_usage(conn, tenant_id, response, user_id=user_id, input_text=prompt)
            text = response.text.strip()
            if text.startswith('```'):
                lines = text.split('\n')
                if lines[0].startswith('```'):
                    lines = lines[1:]
                if lines[-1].startswith('```'):
                    lines = lines[:-1]
                text = '\n'.join(lines).strip()
            return json.loads(text)
        except Exception as e:
            logger.error(f"Industry detection failed: {e}")
            if "LIMIT REACHED" in str(e): raise e
            return {"error": str(e)}

    @staticmethod
    async def generate_document(
        template_content: str, user_input: str, industry_context: str, tenant_id: Any, conn: Any = None, override_prompt: Optional[str] = None, user_id: Any = None
    ) -> str:
        """
        Generate a new document or report based on a template and user input.
        """
        from google.genai import types
        from app.services.db.metering_db_service import MeteringDBService
        
        if conn and tenant_id:
            await MeteringDBService().check_usage_limits(conn, uuid.UUID(str(tenant_id)), "ai")

        prompt = f"Template: {template_content}\nUser Instructions: {user_input}"

        try:
            client = get_genai_client()
            response = await client.aio.models.generate_content(
                model=settings.AI_LLM_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=settings.AI_SYSTEM_PROMPT,
                    temperature=0.7,
                ),
            )
            await LLMService.log_response_usage(conn, tenant_id, response, user_id=user_id, input_text=prompt)
            return response.text.strip()
        except Exception as e:
            logger.error(f"Document generation failed: {e}")
            if "LIMIT REACHED" in str(e): raise e
            return f"Error generating document: {str(e)}"

    @staticmethod
    async def summarize_text(text: str, tenant_id: Any, conn: Any = None, user_id: Any = None) -> str:
        """
        Summarizes the provided text using AI.
        """
        from google.genai import types
        from app.services.db.metering_db_service import MeteringDBService
        
        if conn and tenant_id:
            await MeteringDBService().check_usage_limits(conn, uuid.UUID(str(tenant_id)), "ai")

        prompt = f"{settings.AI_SUMMARIZATION_PROMPT}\nText to summarize: {text}"
        try:
            client = get_genai_client()
            response = await client.aio.models.generate_content(
                model=settings.AI_LLM_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=settings.AI_SYSTEM_PROMPT,
                    temperature=0.3,
                ),
            )
            await LLMService.log_response_usage(conn, tenant_id, response, user_id=user_id, input_text=prompt)
            return response.text.strip()
        except Exception as e:
            logger.error(f"Summarization failed: {e}")
            if "LIMIT REACHED" in str(e): raise e
            return f"Error summarizing: {str(e)}"

    @staticmethod
    async def extract_structured_data(
        text: str, schema: dict, tenant_id: Any, conn: Any = None, user_id: Any = None
    ) -> tuple[dict, int]:
        """
        Extracts structured data from unstructured text based on a provided JSON schema.
        Returns a tuple of (data_dict, tokens_consumed).
        """
        try:
            client = get_genai_client()
            import json
            from google.genai import types
            
            prompt = f"Extract information from the following text strictly according to this JSON schema: {json.dumps(schema)}\n\nText: {text}"
            
            # Check limits before making API call if conn and tenant_id provided
            if conn and tenant_id:
                from app.services.db.metering_db_service import MeteringDBService
                await MeteringDBService().check_usage_limits(conn, uuid.UUID(str(tenant_id)), "ai")
                
            response = await client.aio.models.generate_content(
                model=settings.AI_LLM_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    response_mime_type="application/json"
                )
            )
            
            await LLMService.log_response_usage(conn, tenant_id, response, user_id=user_id, input_text=prompt)
            
            tokens = 0
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                tokens = response.usage_metadata.total_token_count or 0

            text = response.text.strip()
            if text.startswith('```'):
                lines = text.split('\n')
                if lines[0].startswith('```'):
                    lines = lines[1:]
                if lines[-1].startswith('```'):
                    lines = lines[:-1]
                text = '\n'.join(lines).strip()
            
            data = json.loads(text)
            if isinstance(data, list):
                data = data[0] if data else {}
            if not isinstance(data, dict):
                data = {}
            return data, tokens
        except Exception as e:
            logger.error(f"Failed to extract structured data: {e}")
            if "LIMIT REACHED" in str(e):
                raise e
            return {"error": str(e)}, 0

    @staticmethod
    async def generate_suggestions(
        context: str, 
        tenant_id: Any, 
        conn: Any = None, 
        user_id: Any = None,
        max_suggestions: int = 3
    ) -> List[str]:
        """
        Generate proactive follow-up suggestions based on the context.
        """
        from google.genai import types
        from app.services.db.metering_db_service import MeteringDBService
        
        if conn and tenant_id:
            await MeteringDBService().check_usage_limits(conn, uuid.UUID(str(tenant_id)), "ai")

        prompt = f"""
        Based on the following context, generate {max_suggestions} short, proactive follow-up questions or suggestions that a user might want to ask next.
        
        ### CONTEXT:
        {context[:10000]}
        
        ### OUTPUT REQUIREMENTS:
        Return ONLY a JSON array of strings. 
        Example: ["What is the total amount?", "When is the next payment due?", "List the key risks."]
        """

        try:
            client = get_genai_client()
            response = await client.aio.models.generate_content(
                model=settings.AI_LLM_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction="You are a proactive assistant. Only return a valid JSON array of strings.",
                    response_mime_type="application/json",
                    temperature=0.7,
                ),
            )
            await LLMService.log_response_usage(conn, tenant_id, response, user_id=user_id, input_text=prompt)
            
            text = response.text.strip()
            # Clean up potential markdown code blocks
            if text.startswith('```'):
                lines = text.split('\n')
                if lines[0].startswith('```'): lines = lines[1:]
                if lines[-1].startswith('```'): lines = lines[:-1]
                text = '\n'.join(lines).strip()
            
            import json
            suggestions = json.loads(text)
            if isinstance(suggestions, list):
                return [str(s) for s in suggestions[:max_suggestions]]
            return []
        except Exception as e:
            logger.error(f"Generate suggestions failed: {e}")
            return []

    @staticmethod
    async def query_document(context: str, question: str, document_name: str, tenant_id: Any, conn: Any = None, user_id: Any = None) -> str:
        """
        Answer a question about a document using the provided context.
        """
        from google.genai import types
        from app.services.db.metering_db_service import MeteringDBService
        
        if conn and tenant_id:
            await MeteringDBService().check_usage_limits(conn, uuid.UUID(str(tenant_id)), "ai")

        prompt = f"Context: {context}\nQuestion: {question}"

        try:
            client = get_genai_client()
            response = await client.aio.models.generate_content(
                model=settings.AI_LLM_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=f"Answer based ONLY on context from {document_name}",
                    temperature=0.2,
                ),
            )
            await LLMService.log_response_usage(conn, tenant_id, response, user_id=user_id, input_text=prompt)
            return response.text.strip()
        except Exception as e:
            logger.error(f"Document query failed: {e}")
            if "LIMIT REACHED" in str(e): raise e
            return f"Error answering question: {str(e)}"
