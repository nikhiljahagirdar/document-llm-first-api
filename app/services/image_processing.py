import cv2
import os
import io
import numpy as np
from PIL import Image
import pytesseract
try:
    from paddleocr import PaddleOCR
    HAS_PADDLE = True
except ImportError:
    HAS_PADDLE = False

from .llm_service import get_genai_client, types
from app.config import settings

# Lazy initialize PaddleOCR to avoid unnecessary overhead
_paddle_ocr = None

def get_paddle_ocr():
    global _paddle_ocr
    if not HAS_PADDLE:
        return None
    if _paddle_ocr is None:
        # Use language from settings
        _paddle_ocr = PaddleOCR(use_angle_cls=True, lang=settings.OCR_LANGUAGE, show_log=False)
    return _paddle_ocr

async def extract_text_from_image_gemini(image_data: bytes, mime_type: str = "image/png", tenant_id: Any = None, conn: Any = None):
    """
    Uses Gemini 2.0 Flash as a robust fallback OCR.
    """
    try:
        from .llm_service import LLMService
        client = get_genai_client()
        actual_mime = "image/png"
        if "jpg" in mime_type or "jpeg" in mime_type: actual_mime = "image/jpeg"
        elif "webp" in mime_type: actual_mime = "image/webp"

        prompt = "Extract all text from this image exactly as it appears."
        response = await client.aio.models.generate_content(
            model=settings.AI_LLM_MODEL,
            contents=[
                types.Part.from_bytes(data=image_data, mime_type=actual_mime),
                prompt
            ],
            config=types.GenerateContentConfig(temperature=0.0)
        )
        if tenant_id:
            await LLMService.log_response_usage(conn, tenant_id, response)
        return {"text": response.text.strip(), "source": "gemini-ocr-fallback"}
    except Exception as e:
        print(f"Gemini Fallback OCR failed: {e}")
        return {"text": "", "error": str(e)}

async def extract_text_from_image(image_data: bytes, mime_type: str = "image/png", preprocess: bool = True, tenant_id: Any = None, conn: Any = None):
    """
    Uses installed OCR (Tesseract and PaddleOCR) for text extraction, with Gemini fallback.
    """
    final_text = ""
    source = "none"
    
    try:
        # Convert bytes to PIL Image
        img = Image.open(io.BytesIO(image_data))
        
        tess_text = ""
        if settings.USE_TESSERACT_OCR:
            try:
                tess_text = pytesseract.image_to_string(img, lang=settings.OCR_LANGUAGE).strip()
            except Exception as te:
                print(f"Tesseract failed: {te}")
        
        paddle_text = ""
        if settings.USE_PADDLE_OCR and HAS_PADDLE:
            try:
                img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
                ocr = get_paddle_ocr()
                if ocr:
                    result = ocr.ocr(img_cv, cls=True)
                    paddle_text_parts = []
                    if result and result[0]:
                        for line in result[0]:
                            paddle_text_parts.append(line[1][0])
                    paddle_text = "\n".join(paddle_text_parts).strip()
            except Exception as pe:
                print(f"PaddleOCR failed: {pe}")
        
        # Combine or choose the best result
        if paddle_text and (not tess_text or len(paddle_text) > len(tess_text) * 1.5):
            final_text = paddle_text
            source = "paddleocr"
        else:
            final_text = tess_text if tess_text else (paddle_text if HAS_PADDLE else "")
            source = "pytesseract" if tess_text else ("paddleocr" if paddle_text else "none")

    except Exception as e:
        print(f"Local OCR attempts failed: {e}")

    # --- GEMINI FALLBACK ---
    if not final_text.strip():
        print("INFO: Local OCR produced no text. Triggering Gemini fallback...")
        gemini_res = await extract_text_from_image_gemini(image_data, mime_type, tenant_id=tenant_id, conn=conn)
        final_text = gemini_res.get("text", "")
        source = gemini_res.get("source", "gemini-error")

    return {
        "text": final_text,
        "source": f"ocr-{source}",
        "format": "plain_text",
    }


async def preprocess_image(image_path: str, output_path: str):
    """
    Standard file-based OpenCV preprocessing.
    """
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError("Image not found or invalid format")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    denoised = cv2.fastNlMeansDenoising(gray, h=10)
    thresh = cv2.adaptiveThreshold(
        denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )

    cv2.imwrite(output_path, thresh)
    return output_path
