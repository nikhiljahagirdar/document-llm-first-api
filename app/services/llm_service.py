import os
import json
import uuid
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Union
from app.config import settings
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.globals import set_llm_cache
from langchain_core.caches import InMemoryCache

logger = logging.getLogger(__name__)

# Setup global LangChain caching layer
try:
    if settings.USE_REDIS:
        try:
            from langchain_community.cache import RedisCache
            import redis
            redis_client = redis.Redis.from_url(settings.REDIS_URL)
            set_llm_cache(RedisCache(redis_client=redis_client))
            print("INFO: LangChain RedisCache initialized successfully.")
        except Exception as cache_err:
            set_llm_cache(InMemoryCache())
            print(f"WARNING: LangChain RedisCache initialization failed, falling back to InMemoryCache: {cache_err}")
    else:
        set_llm_cache(InMemoryCache())
        print("INFO: LangChain InMemoryCache initialized successfully.")
except Exception as e:
    logger.warning(f"Failed to set LangChain cache: {e}")

from langchain_core.callbacks import BaseCallbackHandler

class LoggingCallbackHandler(BaseCallbackHandler):
    def on_llm_start(self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any) -> Any:
        print("\n" + "🚀 " * 10 + "GOOGLE API REQUEST" + " 🚀" * 10)
        for i, prompt in enumerate(prompts):
            print(f"Prompt {i+1}:\n{prompt}")
        print("=" * 60 + "\n")

    def on_chat_model_start(self, serialized: Dict[str, Any], messages: List[List[Any]], **kwargs: Any) -> Any:
        print("\n" + "🚀 " * 10 + "GOOGLE API REQUEST (CHAT)" + " 🚀" * 10)
        for i, msg_list in enumerate(messages):
            print(f"Chat Session {i+1}:")
            for msg in msg_list:
                print(f"  [{getattr(msg, 'type', 'message')}]: {getattr(msg, 'content', '')}")
        print("=" * 60 + "\n")

    def on_llm_end(self, response, **kwargs: Any) -> Any:
        print("\n" + "🎯 " * 10 + "GOOGLE API RESPONSE" + " 🎯" * 10)
        for i, generation in enumerate(response.generations):
            print(f"Generation {i+1}:")
            for gen in generation:
                print(f"  Text: {gen.text}")
        print("=" * 60 + "\n")

def get_llm(temperature: float = 0.7, **kwargs):
    """
    Initializes the LangChain Google GenAI Chat Model with logging callback handler.
    """
    api_key = settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set in settings or environment")
    
    # Langchain looks for this env var automatically
    os.environ["GOOGLE_API_KEY"] = api_key
    
    return ChatGoogleGenerativeAI(
        model=settings.AI_LLM_MODEL,
        temperature=temperature,
        callbacks=[LoggingCallbackHandler()],
        **kwargs
    )

def _extract_text(content) -> str:
    """Helper to safely extract text from LangChain AIMessage content."""
    if isinstance(content, list):
        return "".join([b.get("text", "") for b in content if isinstance(b, dict) and "text" in b])
    return str(content)

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
            # In this FastAPI app, we should always have an event loop.
            logger.warning("Usage logging failed: No running event loop found.")

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
        from app.services.db.metering_db_service import MeteringDBService
        
        # Check Limits
        if conn and tenant_id:
            is_valid = await MeteringDBService().check_usage_limits(conn, uuid.UUID(str(tenant_id)), "ai")
            if is_valid is False:
                return {"error": "LIMIT_REACHED: AI Usage token limit exceeded. Please upgrade your plan."}

        system_instruction = f"{settings.AI_SYSTEM_PROMPT}\n{settings.AI_TEMPLATE_SYSTEM_PROMPT}"

        if user_prompt and not (industry or category or subcategory):
            prompt = settings.AI_TEMPLATE_USER_PROMPT_FORMAT.replace(r"\n", "\n").format(user_prompt=user_prompt)
        elif override_prompt:
            prompt = settings.AI_TEMPLATE_OVERRIDE_PROMPT_FORMAT.replace(r"\n", "\n").format(
                override_prompt=override_prompt,
                industry=industry,
                category=category,
                subcategory=subcategory
            )
        else:
            prompt = settings.AI_TEMPLATE_STANDARD_PROMPT_FORMAT.replace(r"\n", "\n").format(
                industry=industry,
                category=category,
                subcategory=subcategory
            )

        try:
            llm = get_llm(temperature=0.7).bind(response_mime_type="application/json")
            messages = [
                SystemMessage(content=system_instruction),
                HumanMessage(content=prompt)
            ]
            response = await llm.ainvoke(messages)
            await LLMService.log_response_usage(conn, tenant_id, response, user_id=user_id, input_text=prompt)
            text = _extract_text(response.content).strip()
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
            if isinstance(usage, dict):
                total_tokens = usage.get('total_tokens', 0)
                input_tokens = usage.get('input_tokens', 0)
            else:
                total_tokens = getattr(usage, 'total_tokens', 0) or getattr(usage, 'total_token_count', 0)
                input_tokens = getattr(usage, 'input_tokens', 0) or getattr(usage, 'prompt_token_count', 0)

            try:
                if total_tokens:
                    output_text = _extract_text(response.content) if hasattr(response, 'content') else None
                    await LLMService.log_llm_usage(conn, tenant_id, "AI Usage (Tokens)", total_tokens, user_id, input_text, output_text)
                if input_tokens:
                    await LLMService.log_llm_usage(conn, tenant_id, "prompt_tokens", input_tokens, user_id)
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
            from app.db_raw import DBWrapper, get_connection
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
                async with get_connection() as new_conn:
                    await DBWrapper.execute(new_conn, sql, params)
            elif hasattr(conn, 'execute') and not hasattr(conn, 'cursor'):
                # Assume asyncpg connection
                await DBWrapper.execute(conn, sql, params)
            elif hasattr(conn, 'cursor') and not hasattr(conn, '__aenter__'):
                # Sync connection
                with conn.cursor() as cur:
                    cur.execute(sql, params)
            else:
                # Fallback
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
        from app.services.db.metering_db_service import MeteringDBService
        
        # Check Limits
        if conn and tenant_id:
            is_valid = await MeteringDBService().check_usage_limits(conn, uuid.UUID(str(tenant_id)), "ai")
            if is_valid is False:
                return {"error": "LIMIT_REACHED: AI Usage token limit exceeded. Please upgrade your plan."}

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
            classification_list = []
            for i in industries_or_subcategories:
                if not isinstance(i, dict): continue
                
                cat_raw = i.get("categories") or []
                if isinstance(cat_raw, str):
                    try: cat_raw = json.loads(cat_raw)
                    except: cat_raw = []
                
                processed_cats = []
                for c in (cat_raw if isinstance(cat_raw, list) else []):
                    if not isinstance(c, dict): continue
                    
                    sub_raw = c.get("subcategories") or []
                    if isinstance(sub_raw, str):
                        try: sub_raw = json.loads(sub_raw)
                        except: sub_raw = []
                        
                    processed_subs = []
                    for s in (sub_raw if isinstance(sub_raw, list) else []):
                         if isinstance(s, dict):
                             processed_subs.append({"id": str(s.get("subcategory_id")), "name": s.get("name")})
                             
                    processed_cats.append({
                        "id": str(c.get("category_id")),
                        "name": c.get("name"),
                        "subcategories": processed_subs
                    })
                
                classification_list.append({
                    "id": str(i.get("industry_id")),
                    "name": i.get("name"),
                    "categories": processed_cats
                })

        prompt = settings.AI_CLASSIFICATION_PROMPT_FORMAT.replace(r"\n", "\n").format(
            classification_list=json.dumps(classification_list, indent=2),
            text=text[:8000]
        )

        try:
            llm = get_llm(temperature=0.1).bind(response_mime_type="application/json")
            messages = [
                SystemMessage(content=settings.AI_CLASSIFICATION_SYSTEM_PROMPT),
                HumanMessage(content=prompt)
            ]
            response = await llm.ainvoke(messages)
            await LLMService.log_response_usage(conn, tenant_id, response, user_id=user_id, input_text=prompt)
            text = _extract_text(response.content).strip()
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
        from app.services.db.metering_db_service import MeteringDBService
        
        if conn and tenant_id:
            is_valid = await MeteringDBService().check_usage_limits(conn, uuid.UUID(str(tenant_id)), "ai")
            if is_valid is False:
                return "Error: LIMIT_REACHED: AI Usage token limit exceeded. Please upgrade your plan."

        prompt = f"Template: {template_content}\nUser Instructions: {user_input}"

        try:
            llm = get_llm(temperature=0.7)
            messages = [
                SystemMessage(content=settings.AI_SYSTEM_PROMPT),
                HumanMessage(content=prompt)
            ]
            response = await llm.ainvoke(messages)
            await LLMService.log_response_usage(conn, tenant_id, response, user_id=user_id, input_text=prompt)
            return _extract_text(response.content).strip()
        except Exception as e:
            logger.error(f"Document generation failed: {e}")
            if "LIMIT REACHED" in str(e): raise e
            return f"Error generating document: {str(e)}"

    @staticmethod
    async def summarize_text(text: str, tenant_id: Any, conn: Any = None, user_id: Any = None) -> str:
        """
        Summarizes the provided text using AI.
        """
        from app.services.db.metering_db_service import MeteringDBService
        
        if conn and tenant_id:
            is_valid = await MeteringDBService().check_usage_limits(conn, uuid.UUID(str(tenant_id)), "ai")
            if is_valid is False:
                return "Error: LIMIT_REACHED: AI Usage token limit exceeded. Please upgrade your plan."

        prompt = f"{settings.AI_SUMMARIZATION_PROMPT}\nText to summarize: {text}"
        try:
            llm = get_llm(temperature=0.3)
            messages = [
                SystemMessage(content=settings.AI_SYSTEM_PROMPT),
                HumanMessage(content=prompt)
            ]
            response = await llm.ainvoke(messages)
            await LLMService.log_response_usage(conn, tenant_id, response, user_id=user_id, input_text=prompt)
            return _extract_text(response.content).strip()
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
            import json
            
            prompt = f"Extract information from the following text strictly according to this JSON schema: {json.dumps(schema)}\n\nText: {text}"
            
            # Check limits before making API call if conn and tenant_id provided
            if conn and tenant_id:
                from app.services.db.metering_db_service import MeteringDBService
                is_valid = await MeteringDBService().check_usage_limits(conn, uuid.UUID(str(tenant_id)), "ai")
                if is_valid is False:
                    return {"error": "LIMIT_REACHED: AI Usage token limit exceeded. Please upgrade your plan."}, 0
                
            # Pass schema to response_schema for native structured output binding
            llm = get_llm(temperature=0.0).bind(response_mime_type="application/json", response_schema=schema)
            response = await llm.ainvoke(prompt)
            
            await LLMService.log_response_usage(conn, tenant_id, response, user_id=user_id, input_text=prompt)
            
            tokens = 0
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                tokens = getattr(response.usage_metadata, 'total_tokens', 0) or getattr(response.usage_metadata, 'total_token_count', 0)

            text = _extract_text(response.content).strip()
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
        from app.services.db.metering_db_service import MeteringDBService
        
        if conn and tenant_id:
            is_valid = await MeteringDBService().check_usage_limits(conn, uuid.UUID(str(tenant_id)), "ai")
            if is_valid is False:
                return ["LIMIT_REACHED: AI Usage token limit exceeded. Please upgrade your plan."]

        prompt = settings.AI_SUGGESTIONS_PROMPT_FORMAT.replace(r"\n", "\n").format(
            max_suggestions=max_suggestions,
            context=context[:10000]
        )

        try:
            llm = get_llm(temperature=0.7).bind(response_mime_type="application/json")
            messages = [
                SystemMessage(content=settings.AI_SUGGESTIONS_SYSTEM_PROMPT),
                HumanMessage(content=prompt)
            ]
            response = await llm.ainvoke(messages)
            await LLMService.log_response_usage(conn, tenant_id, response, user_id=user_id, input_text=prompt)
            
            text = _extract_text(response.content).strip()
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
        from app.services.db.metering_db_service import MeteringDBService
        
        if conn and tenant_id:
            is_valid = await MeteringDBService().check_usage_limits(conn, uuid.UUID(str(tenant_id)), "ai")
            if is_valid is False:
                return "Error: LIMIT_REACHED: AI Usage token limit exceeded. Please upgrade your plan."

        prompt = f"Context: {context}\nQuestion: {question}"

        try:
            llm = get_llm(temperature=0.2)
            messages = [
                SystemMessage(content=f"Answer based ONLY on context from {document_name}"),
                HumanMessage(content=prompt)
            ]
            response = await llm.ainvoke(messages)
            await LLMService.log_response_usage(conn, tenant_id, response, user_id=user_id, input_text=prompt)
            return _extract_text(response.content).strip()
        except Exception as e:
            logger.error(f"Document query failed: {e}")
            if "LIMIT REACHED" in str(e): raise e
            return f"Error answering question: {str(e)}"

    @staticmethod
    async def analyze_multimodal(
        text: str, image_urls: List[str], tenant_id: Any, conn: Any = None, user_id: Any = None
    ) -> Union[str, Dict[str, Any]]:
        """
        Performs deep analysis on a combination of document text and multiple associated images.
        Uses storage services to fetch image bytes and passes them to Langchain LLM services.
        """
        from app.services.db.metering_db_service import MeteringDBService
        from app.services.storage_service import get_file_from_s3, get_s3_key_from_url
        import base64
        import mimetypes

        if conn and tenant_id:
            is_valid = await MeteringDBService().check_usage_limits(conn, uuid.UUID(str(tenant_id)), "ai")
            if is_valid is False:
                return {"error": "LIMIT_REACHED: AI Usage token limit exceeded. Please upgrade your plan."}

        try:
            llm = get_llm(temperature=0.4)
            content_parts = [{"type": "text", "text": text}] if text else []
            
            for url in image_urls:
                s3_key = get_s3_key_from_url(url)
                if s3_key:
                    image_bytes = await get_file_from_s3(s3_key)
                    if image_bytes:
                        mime_type, _ = mimetypes.guess_type(url)
                        if not mime_type:
                            mime_type = "image/jpeg"
                            
                        image_base64 = base64.b64encode(image_bytes).decode("utf-8")
                        content_parts.append({
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime_type};base64,{image_base64}"}
                        })
            
            messages = [
                SystemMessage(content=settings.AI_MULTIMODAL_SYSTEM_PROMPT),
                HumanMessage(content=content_parts)
            ]
            
            response = await llm.ainvoke(messages)
            await LLMService.log_response_usage(conn, tenant_id, response, user_id=user_id, input_text=text)
            
            return _extract_text(response.content).strip()
            
        except Exception as e:
            logger.error(f"Multimodal analysis failed: {e}")
            if "LIMIT REACHED" in str(e): raise e
            return {"error": str(e)}
