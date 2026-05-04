from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
import psycopg
from app.db_raw import get_raw_db
from app.schemas import UserResponse, UserCreate, UserUpdate, Token
from app.dependencies import get_current_user, get_current_tenant
from app.security import (
    get_password_hash, 
    verify_password, 
    create_access_token
)
from app.config import settings
from typing import List, Optional, Any
import uuid
from datetime import datetime, timedelta
from app.services.db.user_db_service import UserDBService
from app.services.db.tenant_db_service import TenantDBService
from app.services.db.audit_log_db_service import AuditLogDBService

router = APIRouter(prefix="/users", tags=["users"])

async def get_user_service():
    return UserDBService()

async def get_tenant_service():
    return TenantDBService()

@router.post(
    "/register", 
    response_model=UserResponse,
    responses={
        400: {"description": "Email already registered", "model": dict},
        422: {"$ref": "#/components/responses/ValidationError"},
        500: {"$ref": "#/components/responses/InternalServerError"}
    },
    summary="Register a new user",
    description="""
    Register a new user in the system. If no tenant_id is provided, a personal tenant
    will be automatically created for the user.
    
    **Requirements:**
    - Email must be unique across the system
    - Password must be at least 8 characters with uppercase, lowercase, and digits
    - First name and last name are optional but recommended
    
    **Response:** Returns the created user information including assigned tenant_id.
    """
)
@router.post("/register/", response_model=UserResponse)
async def register_user(
    user_data: UserCreate, 
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    service: UserDBService = Depends(get_user_service),
    tenant_service: TenantDBService = Depends(get_tenant_service)
):
    # Check if user exists
    existing = await service.get_user_by_email(conn, user_data.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    tenant_id = user_data.tenant_id
    if not tenant_id:
        # If no tenant_id provided, create a personal tenant for this user
        tenant = await tenant_service.create_tenant(conn, {
            "name": f"{user_data.first_name}'s Workspace",
            "slug": f"user-{uuid.uuid4().hex[:8]}"
        })
        tenant_id = tenant["tenant_id"]
    
    hashed_pw = get_password_hash(user_data.password)
    data = user_data.model_dump()
    data.pop("password")
    data["password_hash"] = hashed_pw
    data["tenant_id"] = tenant_id
    if not data.get("user_id"):
        data["user_id"] = str(uuid.uuid4())
    new_user = await service.create_user(conn, data)
    
    # Record Audit Log
    await AuditLogDBService.record_audit_log(
        conn, tenant_id, new_user["user_id"],
        "user_registered", "user", str(new_user["user_id"]),
        {"email": user_data.email}
    )
    
    return new_user

@router.post(
    "/login", 
    response_model=Token,
    responses={
        401: {"description": "Invalid credentials", "model": dict},
        422: {"$ref": "#/components/responses/ValidationError"},
        500: {"$ref": "#/components/responses/InternalServerError"}
    },
    summary="Authenticate user and get JWT token",
    description="""
    Authenticate a user with email and password credentials.
    
    **Requirements:**
    - Valid email and password combination
    - User account must be active
    
    **Response:** Returns JWT access token and user information.
    The token expires in 30 minutes by default.
    
    **Usage:** Include the returned token in the Authorization header for authenticated requests:
    `Authorization: Bearer <access_token>`
    """
)
@router.post("/login/", response_model=Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(), 
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    service: UserDBService = Depends(get_user_service)
):
    user = await service.get_user_by_email(conn, form_data.username)
    if not user or not verify_password(form_data.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    token_str, expire_dt = create_access_token(
        data={"sub": user["email"], "tenant_id": str(user["tenant_id"])}, 
        expires_delta=access_token_expires
    )
    
    # Record Audit Log
    await AuditLogDBService.record_audit_log(
        conn, user["tenant_id"], user["user_id"],
        "user_login", "auth", str(user["user_id"])
    )
    
    # Calculate expires_in in seconds
    expires_in = int(access_token_expires.total_seconds())
    
    return {
        "access_token": token_str, 
        "token_type": "bearer",
        "expires_at": expire_dt,
        "expires_in": expires_in,
        "user": user
    }

@router.get(
    "/me", 
    response_model=UserResponse,
    responses={
        401: {"$ref": "#/components/responses/UnauthorizedError"},
        500: {"$ref": "#/components/responses/InternalServerError"}
    },
    summary="Get current user profile",
    description="""
    Retrieve the profile information of the currently authenticated user.
    
    **Requirements:**
    - Valid JWT token required
    - User account must be active
    
    **Response:** Returns complete user profile including tenant and role information.
    """
)
@router.get("/me/", response_model=UserResponse)
async def read_users_me(current_user: Any = Depends(get_current_user)):
    return current_user

@router.patch(
    "/me", 
    response_model=UserResponse,
    responses={
        401: {"$ref": "#/components/responses/UnauthorizedError"},
        422: {"$ref": "#/components/responses/ValidationError"},
        500: {"$ref": "#/components/responses/InternalServerError"}
    },
    summary="Update current user profile",
    description="""
    Update the profile information of the currently authenticated user.
    Only provided fields will be updated (partial update).
    
    **Requirements:**
    - Valid JWT token required
    - User account must be active
    - Password must meet security requirements if updated
    
    **Response:** Returns updated user profile information.
    """
)
@router.patch("/me/", response_model=UserResponse)
async def update_user_me(
    user_update: UserUpdate,
    current_user: Any = Depends(get_current_user),
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    service: UserDBService = Depends(get_user_service)
):
    update_data = user_update.model_dump(exclude_unset=True)
    if not update_data:
        return current_user

    if "password" in update_data:
        update_data["password_hash"] = get_password_hash(update_data.pop("password"))
    
    updated_user = await service.update_user(conn, current_user.user_id, update_data)
    
    # Record Audit Log
    await AuditLogDBService.record_audit_log(
        conn, current_user.tenant_id, current_user.user_id,
        "user_profile_updated", "user", str(current_user.user_id)
    )
    
    return updated_user

@router.get(
    "/", 
    response_model=List[UserResponse],
    responses={
        401: {"$ref": "#/components/responses/UnauthorizedError"},
        403: {"$ref": "#/components/responses/ForbiddenError"},
        500: {"$ref": "#/components/responses/InternalServerError"}
    },
    summary="List all users in tenant",
    description="""
    Retrieve a list of all users belonging to the current user's tenant.
    Requires appropriate permissions to view other users.
    
    **Requirements:**
    - Valid JWT token required
    - Sufficient role permissions (admin or manager)
    - User account must be active
    
    **Response:** Returns list of user profiles within the tenant.
    """
)
async def list_tenant_users(
    current_user: Any = Depends(get_current_user),
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    service: UserDBService = Depends(get_user_service)
):
    return await service.list_tenant_users(conn, current_user.tenant_id)
