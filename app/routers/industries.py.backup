from fastapi import APIRouter, Depends, HTTPException, status
from app.schemas import IndustryResponse, IndustryCreate, IndustryUpdate, TemplateResponse
from typing import List, Optional
import uuid
from fastapi_cache.decorator import cache
import psycopg
from app.db_raw import get_raw_db
from app.services.db.industry_db_service import IndustryDBService

router = APIRouter(prefix="/industries", tags=["industries"])

async def get_industry_service():
    return IndustryDBService()

# --- Industry Endpoints ---

@router.get("", response_model=List[IndustryResponse])
@router.get("/", response_model=List[IndustryResponse])
async def get_all_industries(
    search: Optional[str] = None,
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    service: IndustryDBService = Depends(get_industry_service)
):
    """
    List all supported industries and their associated categories with optional search.
    """
    return await service.list_industries(conn, search)

@router.post("", response_model=IndustryResponse, status_code=status.HTTP_201_CREATED)
async def create_industry(
    industry: IndustryCreate, 
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    service: IndustryDBService = Depends(get_industry_service)
):
    """
    Create a new industry.
    """
    return await service.create_industry(conn, industry.model_dump())

@router.get("/{industry_id}", response_model=IndustryResponse)
async def get_industry(
    industry_id: uuid.UUID, 
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    service: IndustryDBService = Depends(get_industry_service)
):
    """
    Retrieve a specific industry by ID.
    """
    industry = await service.get_industry(conn, industry_id)
    if not industry:
        raise HTTPException(status_code=404, detail="Industry not found")
    return industry

@router.patch("/{industry_id}", response_model=IndustryResponse)
async def update_industry(
    industry_id: uuid.UUID, 
    industry_update: IndustryUpdate, 
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    service: IndustryDBService = Depends(get_industry_service)
):
    """
    Update industry details.
    """
    # Verify existence
    existing = await service.get_industry(conn, industry_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Industry not found")
    
    update_data = industry_update.model_dump(exclude_unset=True)
    return await service.update_industry(conn, industry_id, update_data)

@router.delete("/{industry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_industry(
    industry_id: uuid.UUID, 
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    service: IndustryDBService = Depends(get_industry_service)
):
    """
    Delete an industry.
    """
    # Verify existence
    existing = await service.get_industry(conn, industry_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Industry not found")
    
    await service.delete_industry(conn, industry_id)
    return None

@router.get("/{industry_id}/templates", response_model=List[TemplateResponse])
async def get_templates_by_industry(
    industry_id: uuid.UUID, 
    tenant_id: Optional[uuid.UUID] = None, 
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    service: IndustryDBService = Depends(get_industry_service)
):
    """
    Retrieve document templates associated with a specific industry.
    """
    # Verify industry exists
    industry = await service.get_industry(conn, industry_id)
    if not industry:
        raise HTTPException(status_code=404, detail="Industry not found")

    return await service.get_industry_templates(conn, industry_id, tenant_id)
