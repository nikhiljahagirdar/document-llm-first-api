import os
import uuid
import hashlib
from typing import Dict, Any, Optional, Tuple, Union, List
import nltk
from nltk import word_tokenize, pos_tag, sent_tokenize
from haystack_integrations.document_stores.pgvector import PgvectorDocumentStore
from haystack_integrations.document_stores.pgvector.filters import _convert_filters_to_where_clause_and_params
from haystack_integrations.document_stores.pgvector.document_store import KEYWORD_QUERY
from psycopg.sql import SQL, Composed, Identifier, Literal as SQLLiteral
from haystack import component
from haystack.dataclasses.document import Document
from haystack.document_stores.types import DuplicatePolicy

# Ensure NLTK data is downloaded
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')
    nltk.download('punkt_tab')

try:
    nltk.data.find('taggers/averaged_perceptron_tagger_eng')
except LookupError:
    nltk.download('averaged_perceptron_tagger_eng')

@component
class NLTKDocumentSplitter:
    """
    Custom Haystack component that uses NLTK for high-quality sentence-based splitting.
    Ensures chunks don't break in the middle of a sentence.
    """
    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 150):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    @component.output_types(documents=List[Document])
    def run(self, documents: List[Document]):
        split_docs = []
        for doc in documents:
            sentences = sent_tokenize(doc.content)
            current_chunk = ""
            for sentence in sentences:
                if len(current_chunk) + len(sentence) <= self.chunk_size:
                    current_chunk += sentence + " "
                else:
                    if current_chunk:
                        split_docs.append(Document(content=current_chunk.strip(), meta=doc.meta))
                    
                    if len(sentence) > self.chunk_size:
                        words = sentence.split()
                        sub_chunk = ""
                        for word in words:
                            if len(sub_chunk) + len(word) <= self.chunk_size:
                                sub_chunk += word + " "
                            else:
                                split_docs.append(Document(content=sub_chunk.strip(), meta=doc.meta))
                                sub_chunk = word + " "
                        current_chunk = sub_chunk
                    else:
                        current_chunk = sentence + " "
            
            if current_chunk:
                split_docs.append(Document(content=current_chunk.strip(), meta=doc.meta))
        
        return {"documents": split_docs}

class CustomPgvectorDocumentStore(PgvectorDocumentStore):
    def _build_keyword_retrieval_query(
        self, query: str, top_k: int, filters: Optional[Dict[str, Any]] = None
    ) -> Tuple[Composed, tuple]:
        """
        Subclasses PgvectorDocumentStore to use PostgreSQL's websearch_to_tsquery.
        """
        KEYWORD_QUERY_CUSTOM = """
        SELECT {table_name}.*, ts_rank_cd(to_tsvector({language}, content), query) AS score
        FROM {schema_name}.{table_name}, websearch_to_tsquery({language}, %s) query
        """
        
        sql_select = SQL(KEYWORD_QUERY_CUSTOM).format(
            schema_name=Identifier(self.schema_name),
            table_name=Identifier(self.table_name),
            language=SQLLiteral(self.language),
        )

        where_params = ()
        sql_where_clause: Union[Composed, SQL] = SQL("")
        if filters:
            if "operator" not in filters and "field" not in filters:
                 normalized_filters = {
                     "operator": "AND",
                     "conditions": [{"field": k, "operator": "==", "value": v} for k, v in filters.items()]
                 }
            else:
                 normalized_filters = filters

            sql_where_clause, where_params = _convert_filters_to_where_clause_and_params(
                filters=normalized_filters
            )
            
            self._ensure_db_setup()
            sql_str = sql_where_clause.as_string(self._connection)
            
            if "meta->>" in sql_str:
                sql_str = sql_str.replace("meta->>'tenant_id'", "tenant_id::text")
                sql_str = sql_str.replace("meta->>'document_id'", "document_id::text")
                sql_str = sql_str.replace("meta->>'version_id'", "version_id::text")
                sql_where_clause = SQL(sql_str)

        sql_sort = SQL(" ORDER BY score DESC LIMIT {top_k}").format(top_k=SQLLiteral(top_k))
        sql_query = sql_select + sql_where_clause + sql_sort

        return sql_query, where_params

    def write_documents(self, documents: List[Document], policy: DuplicatePolicy = DuplicatePolicy.NONE) -> int:
        """
        Custom write_documents for document_chunks table.
        """
        if not documents:
            print("DEBUG: No documents to write")
            return 0
            
        print(f"DEBUG: writing {len(documents)} documents to {self.table_name}")
        self._ensure_db_setup()
        
        INSERT_SQL = """
        INSERT INTO {schema_name}.{table_name}
        (chunk_id, embedding, content, document_id, version_id, tenant_id)
        VALUES (%(chunk_id)s, %(embedding)s, %(content)s, %(document_id)s::uuid, %(version_id)s::uuid, %(tenant_id)s::uuid)
        ON CONFLICT (chunk_id) DO UPDATE SET
        embedding = EXCLUDED.embedding,
        content = EXCLUDED.content,
        document_id = EXCLUDED.document_id,
        version_id = EXCLUDED.version_id,
        tenant_id = EXCLUDED.tenant_id
        """
        
        sql_query = SQL(INSERT_SQL).format(
            schema_name=Identifier(self.schema_name),
            table_name=Identifier(self.table_name)
        )
        
        params = []
        for doc in documents:
            chunk_id = doc.id
            try:
                uuid.UUID(chunk_id)
            except ValueError:
                chunk_id = str(uuid.UUID(hashlib.md5(chunk_id.encode()).hexdigest()))
                
            p = {
                "chunk_id": chunk_id,
                "embedding": doc.embedding,
                "content": doc.content,
                "document_id": doc.meta.get("document_id"),
                "version_id": doc.meta.get("version_id"),
                "tenant_id": doc.meta.get("tenant_id")
            }
            params.append(p)
            
        try:
            with self._connection.cursor() as cur:
                cur.executemany(sql_query, params)
            return len(documents)
        except Exception as e:
            print(f"ERROR: Custom write_documents failed: {e}")
            return 0

    def _execute_sql(self, cursor: Any, sql_query: Any, params: Any = None, error_msg: str = "") -> Any:
        # Prevent double WHERE in some Haystack versions if possible, 
        # but here we mostly want to catch the retrieval mapping.
        return super()._execute_sql(cursor, sql_query, params, error_msg)

    def _keyword_retrieval(self, query: str, filters: dict[str, Any] | None = None, top_k: int = 10) -> list[Document]:
        """
        Override keyword retrieval to handle document_chunks table mapping.
        """
        sql_query, where_params = self._build_keyword_retrieval_query(query=query, top_k=top_k, filters=filters)
        
        # In keyword retrieval, query is usually the first param
        params = (query,) + where_params

        try:
            with self._connection.cursor() as cur:
                cur.execute(sql_query, params)
                records = cur.fetchall()
                
                # Manual conversion from record to Document
                # Column order: chunk_id, document_id, version_id, tenant_id, content, embedding, page_number, created_on, score
                # Actually SELECT * order depends on table. 
                # Let's use column names if it's a DictCursor, but PgvectorDocumentStore usually uses standard cursor.
                
                # Check column names
                colnames = [desc[0] for desc in cur.description]
                
                documents = []
                for row in records:
                    row_dict = dict(zip(colnames, row))
                    doc = Document(
                        id=str(row_dict.get("chunk_id")),
                        content=row_dict.get("content"),
                        embedding=row_dict.get("embedding"),
                        meta={
                            "document_id": str(row_dict.get("document_id")),
                            "version_id": str(row_dict.get("version_id")),
                            "tenant_id": str(row_dict.get("tenant_id")),
                            "page_number": row_dict.get("page_number")
                        },
                        score=row_dict.get("score")
                    )
                    documents.append(doc)
                return documents
        except Exception as e:
            print(f"ERROR: Custom keyword retrieval failed: {e}")
            return []

    def _embedding_retrieval(
        self,
        query_embedding: list[float],
        filters: dict[str, Any] | None = None,
        top_k: int = 10,
        vector_function: str | None = None,
    ) -> list[Document]:
        """
        Override embedding retrieval for document_chunks table.
        """
        # Similar logic to _keyword_retrieval but for embeddings
        # For simplicity, let's just use the parent and fix the records if possible, 
        # OR just re-implement. re-implementing is safer for custom schemas.
        
        self._ensure_db_setup()
        
        # Build filter clause
        where_params = ()
        sql_where_clause = SQL("")
        if filters:
            if "operator" not in filters and "field" not in filters:
                 normalized_filters = {
                     "operator": "AND",
                     "conditions": [{"field": k, "operator": "==", "value": v} for k, v in filters.items()]
                 }
            else:
                 normalized_filters = filters
            sql_where_clause, where_params = _convert_filters_to_where_clause_and_params(normalized_filters)
            
            sql_str = sql_where_clause.as_string(self._connection)
            if "meta->>" in sql_str:
                sql_str = sql_str.replace("meta->>'tenant_id'", "tenant_id::text")
                sql_str = sql_str.replace("meta->>'document_id'", "document_id::text")
                sql_str = sql_str.replace("meta->>'version_id'", "version_id::text")
                sql_where_clause = SQL(sql_str)

        # Vector search SQL
        # PostgreSQL with pgvector: <=> is cosine distance, 1 - <=> is cosine similarity
        # Fix: Add explicit cast to ::vector for the parameter %s
        vector_func = vector_function or self.vector_function
        if vector_func == "cosine_similarity":
            score_sql = "1 - (embedding <=> %s::vector)"
        elif vector_func == "inner_product":
            score_sql = "(embedding <#> %s::vector) * -1"
        else: # l2_distance
            score_sql = "embedding <-> %s::vector"

        QUERY_SQL = f"""
        SELECT *, {score_sql} AS score
        FROM {{schema_name}}.{{table_name}}
        """
        
        sql_select = SQL(QUERY_SQL).format(
            schema_name=Identifier(self.schema_name),
            table_name=Identifier(self.table_name)
        )
        
        # Combine
        sql_sort = SQL(" ORDER BY score DESC LIMIT {top_k}").format(top_k=SQLLiteral(top_k))
        sql_query = sql_select + sql_where_clause + sql_sort
        
        params = (query_embedding,) + where_params
        
        try:
            with self._connection.cursor() as cur:
                cur.execute(sql_query, params)
                records = cur.fetchall()
                colnames = [desc[0] for desc in cur.description]
                
                documents = []
                for row in records:
                    row_dict = dict(zip(colnames, row))
                    doc = Document(
                        id=str(row_dict.get("chunk_id")),
                        content=row_dict.get("content"),
                        embedding=row_dict.get("embedding"),
                        meta={
                            "document_id": str(row_dict.get("document_id")),
                            "version_id": str(row_dict.get("version_id")),
                            "tenant_id": str(row_dict.get("tenant_id")),
                            "page_number": row_dict.get("page_number")
                        },
                        score=row_dict.get("score")
                    )
                    documents.append(doc)
                return documents
        except Exception as e:
            print(f"ERROR: Custom embedding retrieval failed: {e}")
            return []

    def embedding_retrieval(self, *args, **kwargs):
        return self._embedding_retrieval(*args, **kwargs)

def extract_keywords(query: str):
    try:
        tokens = word_tokenize(query)
        nouns = [word for word, pos in pos_tag(tokens) if pos.startswith("NN")]
        return nouns[:5]
    except Exception as e:
        print(f"Error extracting keywords: {e}")
        return query.split()[:5]

def transform_query_for_keyword_search(query: str) -> str:
    keywords = extract_keywords(query)
    if not keywords:
        return query
    return " OR ".join(keywords)
