import pymupdf as fitz
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, OcrOptions
import os
import json
import asyncio
from typing import List, Dict, Any, Optional
import gc
import uuid

# Initialize Docling Converter lazily
_docling_converter = None


def get_docling_converter():
    """
    Returns a global Docling DocumentConverter.
    Configured to handle various formats and export to markdown.
    Enabled robust OCR for scanned PDFs and support for Office formats.
    """
    global _docling_converter
    if _docling_converter is None:
        # Enable OCR via Docling. 
        # Using RapidOCR or Tesseract depending on what's available in environment.
        pipeline_options = PdfPipelineOptions(
            do_ocr=True,
            generate_page_images=False,
            generate_picture_images=False,
        )

        _docling_converter = DocumentConverter(
            allowed_formats=[
                InputFormat.PDF,
                InputFormat.DOCX,
                InputFormat.XLSX,
                InputFormat.PPTX,
                InputFormat.IMAGE,
                InputFormat.HTML,
                InputFormat.CSV,
                InputFormat.MD,
            ],
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
                InputFormat.IMAGE: PdfFormatOption(pipeline_options=pipeline_options) # Use same options for images
            },
        )
    return _docling_converter


def extract_csv_text(file_path: str) -> tuple[str, List[dict]]:
    """Fallback CSV parser using pandas for robust extraction. Returns (text, data)."""
    import pandas as pd
    try:
        # Try common encodings
        df = None
        for encoding in ['utf-8', 'latin1', 'cp1252']:
            try:
                # Use engine='python' and sep=None for auto-detection
                # on_bad_lines='skip' ensures we don't fail on malformed rows
                df = pd.read_csv(
                    file_path, 
                    encoding=encoding, 
                    sep=None, 
                    engine='python', 
                    on_bad_lines='skip'
                )
                break
            except (UnicodeDecodeError, pd.errors.ParserError):
                continue
        
        if df is None:
            # Absolute fallback: just read as raw text if pandas fails everything
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
                return content, []
            
        # Convert to string representation (markdown-like table)
        text = df.to_string(index=False)
        
        # Use to_json to ensure pandas types (NaN, datetime, etc) are correctly mapped to JSON types
        json_str = df.to_json(orient='records', date_format='iso')
        data = json.loads(json_str)
        
        return text, data
    except Exception as e:
        print(f"Pandas CSV extraction failed: {e}")
        return "", []


def extract_excel_text(file_path: str) -> tuple[str, dict]:
    """Fallback Excel parser using pandas. Returns (text, data)."""
    import pandas as pd
    try:
        dfs = pd.read_excel(file_path, sheet_name=None)
        text_lines = []
        data = {}
        for sheet_name, df in dfs.items():
            text_lines.append(f"### Sheet: {sheet_name}")
            text_lines.append(df.to_string(index=False))
            text_lines.append("\n")
            
            # Using to_json then json.loads ensures all pandas types (including NaNs, NaTs, dates) 
            # are properly converted to JSON-compliant Python primitives
            json_str = df.to_json(orient='records', date_format='iso')
            data[sheet_name] = json.loads(json_str)
            
        return "\n".join(text_lines), data
    except Exception as e:
        print(f"Pandas Excel extraction failed: {e}")
        return "", {}


def extract_docx_text(file_path: str) -> str:
    """Fallback DOCX parser using python-docx."""
    from docx import Document as DocxDocument
    try:
        doc = DocxDocument(file_path)
        return "\n".join([para.text for para in doc.paragraphs])
    except Exception as e:
        print(f"DOCX fallback extraction failed: {e}")
        return ""


def process_document_to_html_sync(
    file_path: str, file_extension: str
) -> Dict[int, str]:
    """
    Synchronous version of HTML conversion for local libraries.
    If AI fallback is needed, it returns None to signal the async caller.
    """
    html_pages = {}
    ext = file_extension.lower()

    if ext == ".pdf":
        try:
            doc = fitz.open(file_path)
            # Detect if it's a scanned PDF (little to no text)
            total_text = ""
            for page in doc:
                total_text += page.get_text()

            if len(total_text.strip()) < 50 * len(doc):
                doc.close()
                return None  # Trigger AI fallback in async wrapper

            for i, page in enumerate(doc):
                html_pages[i + 1] = page.get_text("html")
            doc.close()
            return html_pages
        except Exception as e:
            print(f"PyMuPDF HTML extraction failed: {e}")
            return None

    elif ext == ".docx":
        try:
            import mammoth

            with open(file_path, "rb") as docx_file:
                result = mammoth.convert_to_html(docx_file)
                return {1: result.value}
        except Exception as e:
            print(f"Mammoth DOCX HTML conversion failed: {e}")
            return None

    return None


async def process_document_to_html(
    file_path: str, file_extension: str, tenant_id: Any = None, conn: Any = None
) -> Dict[int, str]:
    """
    Converts a document to HTML page-by-page.
    Uses asyncio.to_thread for local processing, falls back to AI.
    """
    # Try local sync processing first in a thread
    res = await asyncio.to_thread(process_document_to_html_sync, file_path, file_extension)
    if res is not None:
        return res

    # Fallback to AI
    return await process_document_to_html_ai_fallback(file_path, file_extension, tenant_id=tenant_id, conn=conn)


async def process_document_to_html_ai_fallback(
    file_path: str, file_extension: str, tenant_id: Any = None, conn: Any = None
) -> Dict[int, str]:
    """
    Uses Gemini to convert ANY document to a page-by-page HTML dictionary.
    """
    from app.services.llm_service import get_genai_client, LLMService
    from app.config import settings
    from google.genai import types

    try:
        client = get_genai_client()

        # Standard Gemini MIME types
        mime_map = {
            ".pdf": "application/pdf",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }

        ext = file_extension.lower()
        if ext not in mime_map:
            print(f"WARNING: Gemini AI HTML fallback not supported for {ext}.")
            return {1: "<div>Format not supported for visual preview.</div>"}

        mime_type = mime_map.get(ext, "application/pdf") if ext in mime_map else "application/pdf"

        with open(file_path, "rb") as f:
            file_data = f.read()

        prompt = """
        Analyze the provided document and convert its entire content into HTML use Tables div etc based on the data  smartly analyze.
        1. Process the document PAGE BY PAGE.
        2. Return ONLY a JSON object where keys are page numbers (as strings) and values are the HTML content for that page.
        3. Use professional, clean HTML with inline CSS if necessary for layout (tables, headers).
        4. Maintain structural integrity.
        5. Do NOT include <html>, <head>, or <body> tags. The HTML must be safe to embed directly inside a React component (e.g., wrap each page in a <div>).
        """

        response = await client.aio.models.generate_content(
            model=settings.AI_LLM_MODEL,
            contents=[
                types.Part.from_bytes(data=file_data, mime_type=mime_type),
                prompt,
            ],
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )

        if tenant_id:
            await LLMService.log_response_usage(conn, tenant_id, response)

        try:
            text = response.text.strip()
            if text.startswith('```'):
                lines = text.split('\n')
                if lines[0].startswith('```'):
                    lines = lines[1:]
                if lines[-1].startswith('```'):
                    lines = lines[:-1]
                text = '\n'.join(lines).strip()
            raw_json = json.loads(text)
            return {int(k): v for k, v in raw_json.items()}
        except:
            return {1: f"<div>{response.text}</div>"}

    except Exception as e:
        print(f"AI HTML fallback failed: {e}")
        return {1: f"<p>Error during HTML conversion: {e}</p>"}


async def generate_page_previews(file_path: str, tenant_id: uuid.UUID, document_id: uuid.UUID) -> Optional[str]:
    """
    Renders the first page of a document (PDF) to a PNG thumbnail and uploads to S3.
    Returns the S3 URL of the thumbnail.
    """
    from app.services.storage_service import upload_to_s3
    
    ext = os.path.splitext(file_path)[1].lower()
    thumb_path = f"thumb_{document_id}.png"
    
    try:
        if ext == ".pdf":
            doc = fitz.open(file_path)
            if len(doc) > 0:
                page = doc[0]
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2)) # Higher resolution
                pix.save(thumb_path)
            doc.close()
        elif ext in [".jpg", ".jpeg", ".png", ".webp"]:
            # For images, the thumbnail is just a copy or resize, but we can just use the image itself
            # or make a small version. For now, let's just use fitz if possible or skip.
            return None 

        if os.path.exists(thumb_path):
            s3_key = f"tenant-{tenant_id}/documents/{document_id}/thumbnail.png"
            s3_url = await upload_to_s3(thumb_path, s3_key)
            os.remove(thumb_path)
            return s3_url
    except Exception as e:
        print(f"Thumbnail generation failed: {e}")
        if os.path.exists(thumb_path):
            os.remove(thumb_path)
    
    return None


async def extract_and_upload_images(file_path: str, tenant_id: uuid.UUID, document_id: uuid.UUID) -> Dict[int, List[str]]:
    """
    Extracts images from PDF and uploads them to S3.
    Returns a dictionary mapping page numbers to a list of S3 URLs.
    """
    from app.services.storage_service import upload_to_s3
    
    page_images = {}
    try:
        doc = fitz.open(file_path)
        for page_index in range(len(doc)):
            page_num = page_index + 1
            images = doc.get_page_images(page_index)
            
            for img_index, img in enumerate(images):
                xref = img[0]
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                image_ext = base_image["ext"]
                
                temp_img_path = f"temp_img_{document_id}_{page_num}_{img_index}.{image_ext}"
                with open(temp_img_path, "wb") as f:
                    f.write(image_bytes)
                
                s3_key = f"tenant-{tenant_id}/documents/{document_id}/assets/page_{page_num}_img_{img_index}.{image_ext}"
                s3_url = await upload_to_s3(temp_img_path, s3_key)
                
                if page_num not in page_images:
                    page_images[page_num] = []
                page_images[page_num].append(s3_url)
                
                if os.path.exists(temp_img_path):
                    os.remove(temp_img_path)
        doc.close()
    except Exception as e:
        print(f"Image extraction failed: {e}")
    
    return page_images


def clean_markdown_to_plain_text(md_text: str) -> str:
    """
    Strips basic markdown syntax to provide a cleaner 'plain text' version.
    """
    import re
    # Remove images: ![alt](url)
    text = re.sub(r'!\[.*?\]\(.*?\)', '', md_text)
    # Remove links: [text](url)
    text = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', text)
    # Remove headers: #, ##, etc.
    text = re.sub(r'#+\s*', '', text)
    # Remove bold/italic: **, *
    text = re.sub(r'(\*\*|\*|__|_)', '', text)
    # Remove horizontal rules
    text = re.sub(r'^-{3,}$', '', text, flags=re.MULTILINE)
    # Remove table formatting (pipes and dashes)
    text = re.sub(r'\|', ' ', text)
    text = re.sub(r'^[-\s|]{3,}$', '', text, flags=re.MULTILINE)
    
    return text.strip()


async def process_document(file_path: str, file_extension: str, tenant_id: uuid.UUID = None, document_id: uuid.UUID = None) -> dict:
    """
    Processes all document types using specialized libraries:
    - PDF: PyMuPDF (for text-based) or Docling with OCR (for scanned).
    - DOCX, XLSX, PPTX, Images: Docling with OCR.
    - CSV, Excel: Dedicated parsers (standard csv, openpyxl).
    """
    ext = file_extension.lower()
    
    page_count = 1
    file_type = ext.lstrip('.')
    metadata = {}
    
    try:
        # 1. Fast-path for CSV and Excel (more reliable than Docling for these)
        if ext == ".csv":
            print(f"INFO: Using dedicated CSV parser for {file_path}")
            text, data = await asyncio.to_thread(extract_csv_text, file_path)
            return {
                "text": text, "plain_text": text, "html": {1: f"<pre>{text}</pre>"},
                "rich_content": {"data": data}, "source": "fallback-csv", "format": "text",
                "page_count": 1, "file_type": file_type, "metadata": metadata
            }
        
        if ext in [".xlsx", ".xls"]:
            print(f"INFO: Using dedicated Excel parser for {file_path}")
            text, data = await asyncio.to_thread(extract_excel_text, file_path)
            return {
                "text": text, "plain_text": text, "html": {1: f"<pre>{text}</pre>"},
                "rich_content": {"sheets": data}, "source": "fallback-excel", "format": "text",
                "page_count": 1, "file_type": file_type, "metadata": metadata
            }

        # 2. Extract metadata and page count for PDFs using PyMuPDF
        if ext == ".pdf":
            try:
                doc = fitz.open(file_path)
                page_count = doc.page_count
                metadata = doc.metadata
                doc.close()
            except Exception as e:
                print(f"PyMuPDF pre-check failed: {e}. Proceeding with Docling.")

        # 3. Use Docling for OCR, images, and Office documents
        print(f"INFO: Using Docling for full extraction ({ext})...")
        markdown_text = ""
        rich_content = {}
        source = f"docling-{ext.lstrip('.')}"
        
        try:
            converter = get_docling_converter()
            result = await asyncio.to_thread(converter.convert, file_path)
            doc = result.document
            markdown_text = doc.export_to_markdown()
            rich_content = doc.export_to_dict()
            page_count = doc.page_count if hasattr(doc, 'page_count') and doc.page_count > 0 else 1
        except Exception as e:
            print(f"DEBUG: Docling failed for {ext}: {e}. Trying fallback...")
            source = "fallback"

        # 4. Fallback logic if Docling returns empty or failed
        if not markdown_text.strip():
            print(f"INFO: Running specialized fallback for {ext}...")
            if ext == ".docx":
                markdown_text = await asyncio.to_thread(extract_docx_text, file_path)
                source = "fallback-docx"
            # (CSV and Excel are already handled above)
        
        if not markdown_text.strip():
            print(f"DEBUG: All extraction methods failed for {file_path}")
            return {
                "text": "", "plain_text": "", "error": "Extraction failed: No text content found", 
                "source": "error", "rich_content": {}, "page_count": 0, "file_type": file_type, "metadata": {}
            }

        # Try to get HTML from PyMuPDF if it's a PDF, as Docling's HTML isn't page-based
        html_pages = {}
        if ext == ".pdf":
            try:
                fitz_doc = fitz.open(file_path)
                for i, page in enumerate(fitz_doc):
                    html_pages[i + 1] = page.get_text("html")
                fitz_doc.close()
            except Exception:
                pass # It's ok if this fails, we have markdown

        return {
            "text": markdown_text,
            "plain_text": clean_markdown_to_plain_text(markdown_text),
            "html": html_pages,
            "rich_content": rich_content,
            "source": source,
            "format": "markdown" if "docling" in source else "text",
            "page_count": page_count,
            "file_type": file_type,
            "metadata": metadata # from fitz if available
        }
    except Exception as e:
        print(f"ERROR: Document processing failed for {file_path}: {e}")
        return {"text": "", "plain_text": "", "error": f"Extraction failed: {e}", "source": "error", "rich_content": {}, "page_count": 0, "file_type": file_type, "metadata": {}}
    finally:
        gc.collect()


async def extract_images_from_pdf(file_path: str, output_dir: str) -> list[str]:
    return []
