import os
from dotenv import load_dotenv
from typing import List, Optional, Any
from pydantic import BaseModel

load_dotenv()

class Settings(BaseModel):
    # App Settings
    PROJECT_NAME: str = "DocIntel AI"
    VERSION: str = "1.0.0"
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL")
    
    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "super-secret-key")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 7200))
    
    # AI Models
    AI_LLM_MODEL: str = os.getenv("AI_LLM_MODEL", "gemini-2.5-flash")
    AI_EMBEDDING_MODEL: str = os.getenv("AI_EMBEDDING_MODEL", "models/gemini-embedding-2")
    AI_IMAGE_MODEL: str = os.getenv("AI_IMAGE_MODEL", "imagen-4.0-generate-001")
    
    # OCR Settings
    OCR_LANGUAGE: str = os.getenv("OCR_LANGUAGE", "en")
    USE_PADDLE_OCR: bool = os.getenv("USE_PADDLE_OCR", "True").lower() == "true"
    USE_TESSERACT_OCR: bool = os.getenv("USE_TESSERACT_OCR", "True").lower() == "true"
    
    # AI Keys
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY")
    
    # AI Customization
    AI_SYSTEM_PROMPT: str = os.getenv("AI_SYSTEM_PROMPT", "You are a highly skilled Document Intelligence Assistant.")
    AI_EXTRACTION_PROMPT: str = os.getenv("AI_EXTRACTION_PROMPT", "Focus on identifying tables and key-value pairs.")
    AI_SUMMARIZATION_PROMPT: str = os.getenv("AI_SUMMARIZATION_PROMPT", "Provide a concise summary of the document.")
    AI_TEMPERATURE: float = float(os.getenv("AI_TEMPERATURE", 0.1))
    
    # Email (SMTP)
    SMTP_HOST: str = os.getenv("SMTP_HOST")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", 587))
    SMTP_USER: str = os.getenv("SMTP_USER")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD")
    SMTP_FROM: str = os.getenv("SMTP_FROM")
    SMTP_TLS: bool = os.getenv("SMTP_TLS", "True").lower() == "true"
    
    # AWS / S3 Storage
    AWS_ACCESS_KEY_ID: str = os.getenv("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY: str = os.getenv("AWS_SECRET_ACCESS_KEY")
    AWS_REGION: str = os.getenv("AWS_REGION", "ap-south-1")
    S3_BUCKET_NAME: str = os.getenv("S3_BUCKET_NAME")
    
    # Stripe
    STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY")
    STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET")
    
    # PayPal
    PAYPAL_CLIENT_ID: str = os.getenv("PAYPAL_CLIENT_ID")
    PAYPAL_CLIENT_SECRET: str = os.getenv("PAYPAL_CLIENT_SECRET")
    PAYPAL_MODE: str = os.getenv("PAYPAL_MODE", "sandbox")
    
    # Redis
    USE_REDIS: bool = os.getenv("USE_REDIS", "False").lower() == "true"
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", 6379))
    REDIS_PASSWORD: str = os.getenv("REDIS_PASSWORD", "")
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")

    # Google Integration
    GOOGLE_CLIENT_ID: Optional[str] = os.getenv("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET: Optional[str] = os.getenv("GOOGLE_CLIENT_SECRET")
    GOOGLE_REDIRECT_URI: Optional[str] = os.getenv("GOOGLE_REDIRECT_URI")

    # Local Storage
    UPLOAD_DIR: str = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads")

settings = Settings()
