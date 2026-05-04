from pydantic import BaseModel, EmailStr, Field, field_validator
from uuid import UUID
from typing import Optional, List
from datetime import datetime
from .role import RoleResponse

class UserBase(BaseModel):
    """Base user schema with common fields."""
    
    email: EmailStr = Field(
        ..., 
        description="User email address for authentication and notifications",
        examples=["user@example.com"]
    )
    first_name: Optional[str] = Field(
        None, 
        max_length=50,
        description="User's first name",
        examples=["John"]
    )
    last_name: Optional[str] = Field(
        None, 
        max_length=50,
        description="User's last name", 
        examples=["Doe"]
    )
    provider: Optional[str] = Field(
        "local", 
        pattern="^(local|google)$",
        description="Authentication provider (local or google)",
        examples=["local"]
    )

class UserCreate(UserBase):
    """Schema for creating a new user."""
    
    password: str = Field(
        ..., 
        min_length=8,
        max_length=128,
        description="Password (min 8 characters, max 128 characters)",
        examples=["SecurePass123!"]
    )
    tenant_id: Optional[UUID] = Field(
        None, 
        description="Optional tenant ID. If not provided, a personal tenant will be created",
        examples=["123e4567-e89b-12d3-a456-426614174000"]
    )
    role_id: Optional[UUID] = Field(
        None, 
        description="Optional role ID within the tenant",
        examples=["123e4567-e89b-12d3-a456-426614174001"]
    )
    
    @field_validator('password')
    @classmethod
    def validate_password(cls, v):
        """Validate password strength."""
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one digit')
        return v

class UserUpdate(BaseModel):
    """Schema for updating user information."""
    
    first_name: Optional[str] = Field(
        None, 
        max_length=50,
        description="Updated first name",
        examples=["Jane"]
    )
    last_name: Optional[str] = Field(
        None, 
        max_length=50,
        description="Updated last name",
        examples=["Smith"]
    )
    password: Optional[str] = Field(
        None, 
        min_length=8,
        max_length=128,
        description="New password (min 8 characters, max 128 characters)",
        examples=["NewSecurePass123!"]
    )
    role_id: Optional[UUID] = Field(
        None, 
        description="Updated role ID within the tenant",
        examples=["123e4567-e89b-12d3-a456-426614174001"]
    )
    is_active: Optional[bool] = Field(
        None, 
        description="Whether the user account is active",
        examples=[True]
    )
    
    @field_validator('password')
    @classmethod
    def validate_password(cls, v):
        """Validate password strength if password is provided."""
        if v is None:
            return v
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one digit')
        return v

class UserResponse(UserBase):
    """Schema for user response data."""
    
    user_id: UUID = Field(
        ..., 
        description="Unique user identifier",
        examples=["123e4567-e89b-12d3-a456-426614174000"]
    )
    tenant_id: UUID = Field(
        ..., 
        description="Tenant ID this user belongs to",
        examples=["123e4567-e89b-12d3-a456-426614174001"]
    )
    role_id: Optional[UUID] = Field(
        None, 
        description="User's role ID within the tenant",
        examples=["123e4567-e89b-12d3-a456-426614174002"]
    )
    role: Optional[RoleResponse] = Field(
        None, 
        description="User's role details"
    )
    role_name: Optional[str] = Field(
        None, 
        description="Helper field for UI - user's role name",
        examples=["Admin"]
    )
    created_on: Optional[datetime] = Field(
        None, 
        description="Timestamp when user was created",
        examples=["2024-01-01T00:00:00Z"]
    )
    is_active: Optional[bool] = Field(
        True, 
        description="Whether the user account is active",
        examples=[True]
    )

    class Config:
        from_attributes = True

class GoogleAuthRequest(BaseModel):
    """Schema for Google OAuth authentication request."""
    
    email: EmailStr = Field(
        ..., 
        description="Google account email address",
        examples=["user@gmail.com"]
    )
    first_name: Optional[str] = Field(
        None, 
        max_length=50,
        description="User's first name from Google profile",
        examples=["John"]
    )
    last_name: Optional[str] = Field(
        None, 
        max_length=50,
        description="User's last name from Google profile",
        examples=["Doe"]
    )
    google_id: str = Field(
        ..., 
        description="Google user ID",
        examples=["123456789012345678901"]
    )
    image_url: Optional[str] = Field(
        None, 
        max_length=500,
        description="Profile image URL from Google",
        examples=["https://lh3.googleusercontent.com/photo.jpg"]
    )
    tenant_id: Optional[UUID] = Field(
        None, 
        description="Optional tenant ID for joining existing tenant during first login",
        examples=["123e4567-e89b-12d3-a456-426614174000"]
    )
