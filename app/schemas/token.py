from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from .user import UserResponse

class Token(BaseModel):
    """JWT token response schema with user information."""
    
    access_token: str = Field(
        ..., 
        description="JWT access token for authentication",
        examples=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."]
    )
    token_type: str = Field(
        "bearer", 
        description="Token type (always 'bearer')",
        examples=["bearer"]
    )
    expires_at: datetime = Field(
        ..., 
        description="Token expiration timestamp (UTC)",
        examples=["2024-01-01T01:00:00Z"]
    )
    expires_in: int = Field(
        ..., 
        description="Token expiration time in seconds",
        examples=[1800]
    )
    user: UserResponse = Field(
        ..., 
        description="Authenticated user information"
    )

class TokenData(BaseModel):
    """Token payload data for internal validation."""
    
    email: Optional[str] = Field(
        None, 
        description="User email from token payload",
        examples=["user@example.com"]
    )
    tenant_id: Optional[str] = Field(
        None, 
        description="Tenant ID from token payload",
        examples=["123e4567-e89b-12d3-a456-426614174001"]
    )
