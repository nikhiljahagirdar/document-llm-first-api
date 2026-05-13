import os
import hashlib
import json
from typing import List, Optional, Any
from fastapi_cache import FastAPICache
import logging

logger = logging.getLogger(__name__)


async def get_text_embedding(text: str) -> List[float]:
    """
    Returns a zero vector — embeddings via Google Cloud are disabled.
    Categorization is handled by Gemini LLM text classification instead.
    Defaulting to 3072 dimensions to match database schema.
    """
    return [0.0] * 3072


async def get_batch_embeddings(texts: List[str]) -> List[List[float]]:
    return [[0.0] * 3072 for _ in texts]


def chunk_text_recursive(
    text: str, chunk_size: int = 1000, chunk_overlap: int = 200
) -> List[str]:
    """
    Recursive Character Text Splitting strategy.
    Tries to split by paragraphs, then sentences, then words to keep semantic meaning.
    """
    if not text:
        return []

    separators = ["\n\n", "\n", ". ", " ", ""]
    final_chunks = []

    def _split_recursive(content: str, current_seps: List[str]):
        if len(content) <= chunk_size:
            final_chunks.append(content)
            return

        sep = current_seps[0]
        new_seps = current_seps[1:]

        splits = content.split(sep) if sep else list(content)

        current_chunk = ""
        for s in splits:
            if len(current_chunk) + len(s) + len(sep) <= chunk_size:
                current_chunk += (sep if current_chunk else "") + s
            else:
                if current_chunk:
                    final_chunks.append(current_chunk)

                # Start new chunk with overlap
                overlap_start = max(0, len(current_chunk) - chunk_overlap)
                overlap_text = current_chunk[overlap_start:]

                if len(s) > chunk_size:
                    # Recursive call for the large split itself
                    _split_recursive(s, new_seps)
                    current_chunk = ""
                else:
                    current_chunk = overlap_text + (sep if overlap_text else "") + s

        if current_chunk:
            final_chunks.append(current_chunk)

    _split_recursive(text, separators)
    return final_chunks


async def answer_with_context(
    query: str, context_chunks: List[str], tenant_id: Any = None, conn: Any = None
) -> str:
    """
    Uses Gemini to answer a query based on context (Async).
    """
    prompt = f"""
    You are a professional Document Intelligence Assistant. 
    Answer the user's question using ONLY the provided context.
    If the context is insufficient, state exactly that.
    
    Context:
    {" --- ".join(context_chunks)}
    
    Question: {query}
    
    Professional Answer:
    """

    try:
        from app.services.llm_service import get_llm, LLMService, _extract_text

        llm = get_llm(temperature=0.2)
        response = await llm.ainvoke(prompt)
        if tenant_id:
            await LLMService.log_response_usage(conn, tenant_id, response)
        return _extract_text(response.content)
    except Exception as e:
        logger.error(f"QA failed: {e}", exc_info=True)
        return f"Error generating answer: {e}"
