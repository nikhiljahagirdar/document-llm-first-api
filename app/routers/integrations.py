from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from app.db_raw import get_raw_db, DBWrapper
from app.dependencies import get_current_user
from app.config import settings
from typing import List, Optional, Any
import uuid
import httpx
from datetime import datetime, timedelta
import os
from pydantic import BaseModel

router = APIRouter(prefix="/integrations", tags=["Integrations"])

class AuthUrlResponse(BaseModel):
    url: str

class CallbackRequest(BaseModel):
    code: str
    state: Optional[str] = None

class GoogleFile(BaseModel):
    id: str
    name: str
    mimeType: str
    thumbnailLink: Optional[str] = None

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"

# Scopes needed for Google Docs/Drive
SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "openid"
]

@router.get("/google/auth-url", response_model=AuthUrlResponse)
async def get_google_auth_url(current_user: Any = Depends(get_current_user)):
    """
    Returns the Google OAuth2 authorization URL to allow the user to grant Drive access.
    """
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI, # Typically handled by frontend or a specific callback endpoint
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": str(current_user.user_id)
    }
    url = f"{GOOGLE_AUTH_URL}?{'&'.join([f'{k}={v}' for k, v in params.items()])}"
    return {"url": url}

@router.post("/google/callback")
async def google_callback(
    request: CallbackRequest,
    current_user: Any = Depends(get_current_user),
    conn: Any = Depends(get_raw_db)
):
    """
    Exchanges the authorization code for tokens and stores them securely.
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "code": request.code,
                "grant_type": "authorization_code",
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            }
        )
        
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail=f"Failed to exchange code: {response.text}")
        
        token_data = response.json()
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 3600)
        expires_at = datetime.now() + timedelta(seconds=expires_in)
        
        # Store in user_credentials
        query = """
            INSERT INTO user_credentials (credential_id, user_id, provider, access_token, refresh_token, expires_at, scopes)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id, provider) DO UPDATE SET
            access_token = EXCLUDED.access_token,
            refresh_token = COALESCE(EXCLUDED.refresh_token, user_credentials.refresh_token),
            expires_at = EXCLUDED.expires_at,
            scopes = EXCLUDED.scopes,
            updated_on = NOW()
        """
        await DBWrapper.execute(
            conn, query, 
            (uuid.uuid4(), current_user.user_id, 'google', access_token, refresh_token, expires_at, SCOPES)
        )
        
        return {"status": "success", "message": "Google Drive authorized successfully"}

@router.post("/google/sync")
async def sync_google_drive(
    background_tasks: BackgroundTasks,
    current_user: Any = Depends(get_current_user),
    conn: Any = Depends(get_raw_db)
):
    """
    Synchronizes Google Drive files with the platform.
    Automatically downloads and processes new or updated files.
    """
    # 1. Get credentials
    query = "SELECT access_token, refresh_token, expires_at FROM user_credentials WHERE user_id = %s AND provider = 'google'"
    creds = await DBWrapper.fetch_one(conn, query, (current_user.user_id,))
    if not creds:
        raise HTTPException(status_code=401, detail="Google Drive not authorized")
    
    access_token = creds["access_token"]
    if creds["expires_at"] < datetime.now():
        # Refresh token (shared logic with list_google_drive_files)
        async with httpx.AsyncClient() as client:
            refresh_res = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "refresh_token": creds["refresh_token"],
                    "grant_type": "refresh_token",
                }
            )
            if refresh_res.status_code == 200:
                new_data = refresh_res.json()
                access_token = new_data["access_token"]
                expires_at = datetime.now() + timedelta(seconds=new_data.get("expires_in", 3600))
                await DBWrapper.execute(
                    conn, 
                    "UPDATE user_credentials SET access_token = %s, expires_at = %s WHERE user_id = %s AND provider = 'google'",
                    (access_token, expires_at, current_user.user_id)
                )

    # 2. Fetch all files from Drive
    async with httpx.AsyncClient() as client:
        q = "(mimeType = 'application/vnd.google-apps.document' or mimeType = 'application/pdf') and trashed = false"
        # We need modifiedTime to compare
        response = await client.get(
            GOOGLE_DRIVE_FILES_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            params={"q": q, "fields": "files(id, name, mimeType, modifiedTime)"}
        )
        
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail=f"Google Drive API error: {response.text}")
            
        drive_files = response.json().get("files", [])

    # 3. Compare and Sync
    from app.services.db.document_db_service import DocumentDBService
    from app.routers.documents import import_google_doc
    from app.schemas.document_report import GoogleDocImportRequest
    
    doc_service = DocumentDBService()
    synced_count = 0
    
    for file in drive_files:
        g_id = file["id"]
        g_name = file["name"]
        # ISO format: 2024-04-26T12:34:56.789Z
        g_modified_str = file["modifiedTime"].replace("Z", "")
        g_modified = datetime.fromisoformat(g_modified_str)
        
        # Check if exists
        existing = await doc_service.get_document_by_google_id(conn, g_id, current_user.tenant_id)
        
        should_import = False
        if not existing:
            should_import = True
            print(f"DEBUG: New Google File detected: {g_name}")
        else:
            # Check if updated in Drive since last sync
            last_sync = existing.get("google_last_modified")
            if not last_sync or g_modified > last_sync:
                should_import = True
                print(f"DEBUG: Updated Google File detected: {g_name}")
        
        if should_import:
            # Trigger import (This uses our existing import_google_doc logic but in background)
            # Actually, we can just call the import logic. 
            # To keep it clean, let's create a background task that does the download/process.
            
            # Since import_google_doc is a router function, we might want to extract its core to a service,
            # but for now we'll just use the GoogleDocImportRequest pattern.
            
            # We need to update the document record with google_file_id and modified time
            # We can't easily call the route function here due to Depends.
            
            # Let's add a specialized background task for Drive Syncing
            from app.services.document_workflow_service import DocumentWorkflowService
            background_tasks.add_task(
                DocumentWorkflowService.process_google_import_background,
                g_id, g_name, g_modified, current_user.tenant_id, current_user.user_id, access_token
            )
            synced_count += 1

    return {"status": "success", "synced_files_queued": synced_count}

@router.get("/google/status")
async def get_google_auth_status(
    current_user: Any = Depends(get_current_user),
    conn: Any = Depends(get_raw_db)
):
    """
    Checks if the user has an active Google Drive authorization.
    """
    query = "SELECT expires_at FROM user_credentials WHERE user_id = %s AND provider = 'google'"
    res = await DBWrapper.fetch_one(conn, query, (current_user.user_id,))
    
    if not res:
        return {"authorized": False}
    
    is_expired = res["expires_at"] < datetime.now()
    return {"authorized": True, "expired": is_expired}

@router.get("/google/files", response_model=List[GoogleFile])
async def list_google_drive_files(
    current_user: Any = Depends(get_current_user),
    conn: Any = Depends(get_raw_db)
):
    """
    Lists the user's Google Docs and PDFs from Drive.
    """
    # 1. Get credentials
    query = "SELECT access_token, refresh_token, expires_at FROM user_credentials WHERE user_id = %s AND provider = 'google'"
    creds = await DBWrapper.fetch_one(conn, query, (current_user.user_id,))
    
    if not creds:
        raise HTTPException(status_code=401, detail="Google Drive not authorized")
    
    access_token = creds["access_token"]
    
    # 2. Refresh if expired
    if creds["expires_at"] < datetime.now():
        if not creds["refresh_token"]:
            raise HTTPException(status_code=401, detail="Session expired. Please re-authorize.")
        
        async with httpx.AsyncClient() as client:
            refresh_res = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "refresh_token": creds["refresh_token"],
                    "grant_type": "refresh_token",
                }
            )
            if refresh_res.status_code != 200:
                raise HTTPException(status_code=401, detail="Failed to refresh token")
            
            new_data = refresh_res.json()
            access_token = new_data["access_token"]
            expires_at = datetime.now() + timedelta(seconds=new_data.get("expires_in", 3600))
            
            await DBWrapper.execute(
                conn, 
                "UPDATE user_credentials SET access_token = %s, expires_at = %s WHERE user_id = %s AND provider = 'google'",
                (access_token, expires_at, current_user.user_id)
            )

    # 3. Fetch files
    async with httpx.AsyncClient() as client:
        # Filter for Google Docs and PDFs
        q = "(mimeType = 'application/vnd.google-apps.document' or mimeType = 'application/pdf') and trashed = false"
        response = await client.get(
            GOOGLE_DRIVE_FILES_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            params={"q": q, "fields": "files(id, name, mimeType, thumbnailLink)"}
        )
        
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail=f"Google Drive API error: {response.text}")
            
        return response.json().get("files", [])
