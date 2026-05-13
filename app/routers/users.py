from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
import logging
from app.db_raw import get_raw_db
from app.schemas import UserResponse, UserCreate, UserUpdate, Token, UserRegisterResponse, GoogleAuthRequest
from app.dependencies import get_current_user, get_current_tenant
from app.security import (
    get_password_hash, 
    verify_password, 
    create_access_token
)
from app.config import settings
from typing import List, Optional, Any
import uuid
import httpx
from datetime import datetime, timedelta
from app.services.db.user_db_service import UserDBService
from app.services.db.tenant_db_service import TenantDBService
from app.services.db.audit_log_db_service import AuditLogDBService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])

async def get_user_service():
    return UserDBService()

async def get_tenant_service():
    return TenantDBService()

@router.post(
    "/register", 
    response_model=UserRegisterResponse,
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
    
    **Response:** Returns the created user information along with a JWT access token for immediate use.
    """
)
async def register_user(
    user_data: UserCreate, 
    conn: Any = Depends(get_raw_db),
    service: UserDBService = Depends(get_user_service),
    tenant_service: TenantDBService = Depends(get_tenant_service)
):
    try:
        # Check if user exists
        existing = await service.get_user_by_email(conn, user_data.email)
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")
        
        tenant_id = user_data.tenant_id
        if not tenant_id:
            # If no tenant_id provided, create a personal tenant for this user
            tenant_name = user_data.org_name or (f"{user_data.first_name}'s Workspace" if user_data.first_name else "My Workspace")
            tenant = await tenant_service.create_tenant(conn, {
                "name": tenant_name,
                "type": user_data.tenant_type,
                "org_name": user_data.org_name,
                "slug": f"user-{uuid.uuid4().hex[:8]}"
            })
            tenant_id = tenant["tenant_id"]
            
            # Initialize default settings for new tenant
            await tenant_service.initialize_tenant_settings(conn, tenant_id)
        
        hashed_pw = get_password_hash(user_data.password)
        data = user_data.model_dump()
        data.pop("password")
        data.pop("tenant_type", None)
        data.pop("org_name", None)
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
        
        # Generate token for immediate use (Stepper flow support)
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        token_str, _ = create_access_token(
            data={"sub": new_user["email"], "tenant_id": str(new_user["tenant_id"])}, 
            expires_delta=access_token_expires
        )
        
        return {
            "user": new_user,
            "access_token": token_str,
            "token_type": "bearer"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")

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
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(), 
    conn: Any = Depends(get_raw_db),
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
async def update_user_me(
    user_update: UserUpdate,
    current_user: Any = Depends(get_current_user),
    conn: Any = Depends(get_raw_db),
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
    "", 
    response_model=List[UserResponse],
    responses={
        401: {"$ref": "#/components/responses/UnauthorizedError"},
        403: {"$ref": "#/components/responses/ForbiddenError"},
        500: {"$ref": "#/components/responses/InternalServerError"}
    },
    summary="List all users",
    description="""
    Retrieve a list of users. 
    - **Tenant Admin:** Locked to users within their own tenant.
    - **Super Admin:** Can optionally provide a `tenant_id` query parameter to filter, or see all users if omitted.
    """
)
async def list_tenant_users(
    tenant_id: Optional[uuid.UUID] = None,
    current_user: Any = Depends(get_current_user),
    conn: Any = Depends(get_raw_db),
    service: UserDBService = Depends(get_user_service)
):
    # Check if user is superadmin
    is_superadmin = current_user.role and current_user.role.key in ["super_admin", "superadmin"]
    
    if is_superadmin:
        # Superadmin can see anyone, or filter by tenant if provided
        target_tenant_id = tenant_id
    else:
        # Everyone else is locked to their own tenant
        target_tenant_id = current_user.tenant_id
        
    return await service.list_tenant_users(conn, target_tenant_id)


@router.post(
    "/google-auth",
    response_model=Token,
    summary="Authenticate or register user via Google OAuth",
    description="""
    Authenticates a user using Google OAuth details.
    If the user already exists (found by google_id or email), they will be logged in.
    If they do not exist, a new user profile (and workspace/tenant if needed) will be created, and then they will be logged in.
    """
)
async def google_auth(
    auth_request: GoogleAuthRequest,
    conn: Any = Depends(get_raw_db),
    service: UserDBService = Depends(get_user_service),
    tenant_service: TenantDBService = Depends(get_tenant_service)
):
    try:
        if auth_request.code:
            # Exchange code for tokens
            async with httpx.AsyncClient() as client:
                token_resp = await client.post("https://oauth2.googleapis.com/token", data={
                    "code": auth_request.code,
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "redirect_uri": "postmessage",
                    "grant_type": "authorization_code"
                })
                token_resp.raise_for_status()
                token_data = token_resp.json()
                access_token = token_data.get("access_token")
                
                # Fetch user info using the access token
                user_resp = await client.get("https://www.googleapis.com/oauth2/v3/userinfo", headers={
                    "Authorization": f"Bearer {access_token}"
                })
                user_resp.raise_for_status()
                user_info = user_resp.json()
                
                auth_request.email = user_info.get("email")
                auth_request.google_id = user_info.get("sub")
                auth_request.first_name = user_info.get("given_name", auth_request.first_name)
                auth_request.last_name = user_info.get("family_name", auth_request.last_name)
                auth_request.image_url = user_info.get("picture", auth_request.image_url)

        if not auth_request.google_id or not auth_request.email:
            raise HTTPException(status_code=400, detail="Missing google_id or email")

        # 1. Check if user already exists
        user = await service.get_user_by_google_id_or_email(conn, auth_request.google_id, auth_request.email)
        
        if user:
            # User exists, update Google details if not set (e.g. if they previously registered via local password)
            update_data = {}
            if not user.get("google_id"):
                update_data["google_id"] = auth_request.google_id
            if auth_request.image_url and not user.get("profile_image"):
                update_data["profile_image"] = auth_request.image_url
            if not user.get("provider") or user.get("provider") == "local":
                update_data["provider"] = "google"
                
            if update_data:
                user = await service.update_user(conn, str(user["user_id"]), update_data)
                
            # Record Audit Log for login
            await AuditLogDBService.record_audit_log(
                conn, user["tenant_id"], user["user_id"],
                "user_login", "auth", str(user["user_id"]),
                {"method": "google_oauth"}
            )
        else:
            # 2. User does not exist, create tenant/workspace and register them
            tenant_id = auth_request.tenant_id
            if not tenant_id:
                # Create a personal tenant for this user
                tenant_name = f"{auth_request.first_name}'s Workspace" if auth_request.first_name else "My Workspace"
                tenant = await tenant_service.create_tenant(conn, {
                    "name": tenant_name,
                    "type": "individual",
                    "org_name": None,
                    "slug": f"user-{uuid.uuid4().hex[:8]}"
                })
                tenant_id = tenant["tenant_id"]
                
                # Initialize default settings for new tenant
                await tenant_service.initialize_tenant_settings(conn, tenant_id)
            
            # Since they login via Google, we generate a secure random password hash
            import secrets
            random_pw = secrets.token_urlsafe(32)
            hashed_pw = get_password_hash(random_pw)
            
            user_data = {
                "user_id": str(uuid.uuid4()),
                "tenant_id": str(tenant_id),
                "email": auth_request.email,
                "password_hash": hashed_pw,
                "first_name": auth_request.first_name,
                "last_name": auth_request.last_name,
                "google_id": auth_request.google_id,
                "profile_image": auth_request.image_url,
                "provider": "google",
                "is_active": True
            }
            
            user = await service.create_user(conn, user_data)
            
            # Record Audit Log for registration
            await AuditLogDBService.record_audit_log(
                conn, tenant_id, user["user_id"],
                "user_registered", "user", str(user["user_id"]),
                {"email": auth_request.email, "method": "google_oauth"}
            )
        
        # 3. Generate JWT access token
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        token_str, expire_dt = create_access_token(
            data={"sub": user["email"], "tenant_id": str(user["tenant_id"])}, 
            expires_delta=access_token_expires
        )
        
        expires_in = int(access_token_expires.total_seconds())
        
        return {
            "access_token": token_str,
            "token_type": "bearer",
            "expires_at": expire_dt,
            "expires_in": expires_in,
            "user": user,
            "google_refresh_token": refresh_token if 'refresh_token' in locals() else None
        }
    except Exception as e:
        logger.error(f"Google authentication failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Google authentication failed: {str(e)}")

