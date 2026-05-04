from typing import Optional, Any
from fastapi import Depends, HTTPException, status, Header
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
import psycopg

from app import security
from app.db_raw import get_raw_db, DBWrapper
from app.services.db.user_db_service import UserDBService
from app.services.db.tenant_db_service import TenantDBService
from app.services.db.role_db_service import RoleDBService

load_dotenv = security.load_dotenv
SECRET_KEY = security.SECRET_KEY
ALGORITHM = security.ALGORITHM

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/users/token", auto_error=False)

# Service Dependencies
async def get_user_service():
    return UserDBService()

async def get_tenant_service():
    return TenantDBService()

async def get_role_service():
    return RoleDBService()

class Map(dict):
    """
    A dictionary that enables dot notation access to its items.
    """
    def __getattr__(self, item):
        try:
            val = self[item]
            if isinstance(val, dict):
                return Map(val)
            if isinstance(val, list):
                return [Map(x) if isinstance(x, dict) else x for x in val]
            return val
        except KeyError:
            return None # Return None if key doesn't exist, like SQLAlchemy attributes

async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    user_service: UserDBService = Depends(get_user_service),
    x_token: Optional[str] = Header(None, alias="X-Token")
) -> Any:
    """Retrieve the current user from the JWT token using raw SQL."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # Allow token from Bearer or X-Token header
    token = token or x_token
    
    if not token:
        raise credentials_exception
        
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    user_dict = await user_service.get_user_by_email(conn, email)
    
    if user_dict is None:
        raise credentials_exception
    
    # Transform to allow dot notation and nested role object
    user = Map(user_dict)
    if user_dict.get("role_id"):
        role_name = user_dict["role_name"]
        user.role = Map({
            "role_id": user_dict["role_id"],
            "name": role_name,
            "key": role_name.lower().replace(" ", "_"), # e.g. "super_admin"
            "permissions": user_dict["role_permissions"]
        })
    else:
        user.role = None
        
    return user


async def get_optional_user(
    token: Optional[str] = Depends(oauth2_scheme),
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    user_service: UserDBService = Depends(get_user_service),
    x_token: Optional[str] = Header(None, alias="X-Token")
) -> Optional[Any]:
    """Retrieve the current user if available, otherwise return None."""
    token = token or x_token
    if not token:
        return None
        
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            return None
    except JWTError:
        return None
        
    user_dict = await user_service.get_user_by_email(conn, email)
    if user_dict is None:
        return None
    
    user = Map(user_dict)
    if user_dict.get("role_id"):
        role_name = user_dict["role_name"]
        user.role = Map({
            "role_id": user_dict["role_id"],
            "name": role_name,
            "key": role_name.lower().replace(" ", "_"), # e.g. "super_admin"
            "permissions": user_dict["role_permissions"]
        })
    else:
        user.role = None
        
    return user


async def get_current_tenant(
    current_user: Any = Depends(get_current_user),
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    tenant_service: TenantDBService = Depends(get_tenant_service)
) -> Any:
    """Retrieve the current tenant for the authenticated user using raw SQL."""
    tenant_dict = await tenant_service.get_tenant_by_id(conn, current_user.tenant_id)
    
    if not tenant_dict:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    return Map(tenant_dict)


async def get_optional_tenant(
    current_user: Optional[Any] = Depends(get_optional_user),
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    tenant_service: TenantDBService = Depends(get_tenant_service)
) -> Optional[Any]:
    """Retrieve the current tenant if available, otherwise return None."""
    if not current_user:
        return None
        
    tenant_dict = await tenant_service.get_tenant_by_id(conn, current_user.tenant_id)
    if not tenant_dict:
        return None
    
    return Map(tenant_dict)


async def get_superadmin(
    current_user: Any = Depends(get_current_user)
) -> Any:
    """Check if the current user has superadmin role."""
    if not current_user.role or current_user.role.key not in ["super_admin", "superadmin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operation not permitted. Superadmin access required."
        )
    return current_user


class RoleChecker:
    """
    Dependency to check if the current user has one of the allowed roles.
    Example: require_admin = RoleChecker(["superadmin", "enterprise_tenant"])
    """
    def __init__(self, allowed_roles: list[str]):
        # Normalize allowed roles for comparison
        self.allowed_roles = [r.lower().replace(" ", "_") for r in allowed_roles]

    def __call__(self, current_user: Any = Depends(get_current_user)) -> Any:
        if not current_user.role or current_user.role.key not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation not permitted. Required roles: {', '.join(self.allowed_roles)}"
            )
        return current_user
