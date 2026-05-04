import uuid
from typing import List, Optional, Any
import psycopg
from fastapi import APIRouter, Depends, HTTPException, status
from app.db_raw import get_raw_db
from app.dependencies import get_current_user, get_current_tenant
from app.schemas import FolderResponse, FolderCreate, FolderUpdate
from app.services.db.folder_db_service import FolderDBService

router = APIRouter(prefix="/folders", tags=["folders"])

async def get_folder_service():
    return FolderDBService()

@router.get("", response_model=List[FolderResponse])
@router.get("/", response_model=List[FolderResponse])
async def list_folders(
    parent_folder_id: Optional[uuid.UUID] = None,
    search: Optional[str] = None,
    tenant: Any = Depends(get_current_tenant),
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    service: FolderDBService = Depends(get_folder_service)
):
    """
    List folders for the current tenant.
    """
    return await service.list_folders(conn, tenant.tenant_id, parent_folder_id, search)

@router.post("", response_model=FolderResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=FolderResponse, status_code=status.HTTP_201_CREATED)
async def create_folder(
    payload: FolderCreate,
    current_user: Any = Depends(get_current_user),
    tenant: Any = Depends(get_current_tenant),
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    service: FolderDBService = Depends(get_folder_service)
):
    """
    Create a new folder.
    """
    return await service.create_folder(
        conn,
        tenant.tenant_id,
        current_user.user_id,
        payload.name,
        payload.description,
        payload.parent_folder_id
    )

@router.get("/{folder_id}", response_model=FolderResponse)
@router.get("/{folder_id}/", response_model=FolderResponse)
async def get_folder(
    folder_id: uuid.UUID,
    tenant: Any = Depends(get_current_tenant),
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    service: FolderDBService = Depends(get_folder_service)
):
    """
    Retrieve a specific folder by ID.
    """
    folder = await service.get_folder(conn, folder_id, tenant.tenant_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    return folder

@router.patch("/{folder_id}", response_model=FolderResponse)
@router.patch("/{folder_id}/", response_model=FolderResponse)
async def update_folder(
    folder_id: uuid.UUID,
    payload: FolderUpdate,
    tenant: Any = Depends(get_current_tenant),
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    service: FolderDBService = Depends(get_folder_service)
):
    """
    Update folder details.
    """
    existing = await service.get_folder(conn, folder_id, tenant.tenant_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Folder not found")
    
    update_data = payload.model_dump(exclude_unset=True)
    return await service.update_folder(conn, folder_id, tenant.tenant_id, update_data)

@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
@router.delete("/{folder_id}/", status_code=status.HTTP_204_NO_CONTENT)
async def delete_folder(
    folder_id: uuid.UUID,
    tenant: Any = Depends(get_current_tenant),
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    service: FolderDBService = Depends(get_folder_service)
):
    """
    Delete a folder. Folder must be empty.
    """
    existing = await service.get_folder(conn, folder_id, tenant.tenant_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Folder not found")
    
    try:
        await service.delete_folder(conn, folder_id, tenant.tenant_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    return None
