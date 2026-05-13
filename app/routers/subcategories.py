from fastapi import APIRouter, Depends, HTTPException, status
from app.db_raw import get_raw_db
from app.schemas import (
    SubcategoryCreate, 
    SubcategoryUpdate, 
    SubcategoryResponse
)
from app.services.db.subcategory_db_service import SubcategoryDBService
from app.services.db.category_db_service import CategoryDBService
from typing import List, Optional, Any
import uuid

router = APIRouter(prefix="/subcategories", tags=["subcategories"])

async def get_subcategory_service():
    return SubcategoryDBService()

async def get_category_service():
    return CategoryDBService()

@router.get("", response_model=List[SubcategoryResponse])
async def list_subcategories(
    conn: Any = Depends(get_raw_db),
    service: SubcategoryDBService = Depends(get_subcategory_service),
    limit: int = 100,
    offset: int = 0,
    search: Optional[str] = None
):
    """
    List all subcategories with pagination and search.
    """
    return await service.list_subcategories(conn, limit, offset, search)

@router.post("", response_model=SubcategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_subcategory(
    subcategory: SubcategoryCreate, 
    conn: Any = Depends(get_raw_db),
    service: SubcategoryDBService = Depends(get_subcategory_service),
    category_service: CategoryDBService = Depends(get_category_service)
):
    """
    Create a new document subcategory within a category.
    """
    # Verify category exists
    category = await category_service.get_category(conn, subcategory.category_id)
    if not category:
        raise HTTPException(status_code=404, detail=f"Category with ID {subcategory.category_id} not found")

    return await service.create_subcategory(
        conn, subcategory.category_id, subcategory.name, subcategory.description, subcategory.prompt
    )

@router.get("/{subcategory_id}", response_model=SubcategoryResponse)
async def get_subcategory(
    subcategory_id: uuid.UUID, 
    conn: Any = Depends(get_raw_db),
    service: SubcategoryDBService = Depends(get_subcategory_service)
):
    """
    Retrieve a specific subcategory.
    """
    subcategory = await service.get_subcategory(conn, subcategory_id)
    if not subcategory:
        raise HTTPException(status_code=404, detail="Subcategory not found")
    return subcategory

@router.patch("/{subcategory_id}", response_model=SubcategoryResponse)
async def update_subcategory(
    subcategory_id: uuid.UUID, 
    subcategory_update: SubcategoryUpdate, 
    conn: Any = Depends(get_raw_db),
    service: SubcategoryDBService = Depends(get_subcategory_service),
    category_service: CategoryDBService = Depends(get_category_service)
):
    """
    Update subcategory details.
    """
    existing = await service.get_subcategory(conn, subcategory_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Subcategory not found")
    
    update_data = subcategory_update.model_dump(exclude_unset=True)
    
    if "category_id" in update_data:
        category = await category_service.get_category(conn, update_data["category_id"])
        if not category:
            raise HTTPException(status_code=404, detail=f"Category with ID {update_data['category_id']} not found")

    return await service.update_subcategory(conn, subcategory_id, update_data)

@router.delete("/{subcategory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_subcategory(
    subcategory_id: uuid.UUID, 
    conn: Any = Depends(get_raw_db),
    service: SubcategoryDBService = Depends(get_subcategory_service)
):
    """
    Delete a subcategory.
    """
    deleted = await service.delete_subcategory(conn, subcategory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Subcategory not found")
    return None
