from fastapi import APIRouter, Depends, HTTPException, status
from app.db_raw import get_raw_db
from app.schemas import (
    CategoryCreate, 
    CategoryUpdate, 
    CategoryResponse,
    SubcategoryResponse
)
from app.services.db.category_db_service import CategoryDBService
from app.services.db.industry_db_service import IndustryDBService
from typing import List, Optional, Any
import uuid

router = APIRouter(prefix="/categories", tags=["categories"])

async def get_category_service():
    return CategoryDBService()

async def get_industry_service():
    return IndustryDBService()

@router.get("", response_model=List[CategoryResponse])
async def list_categories(
    conn: Any = Depends(get_raw_db),
    service: CategoryDBService = Depends(get_category_service),
    limit: int = 100,
    offset: int = 0,
    search: Optional[str] = None
):
    """
    List all categories with pagination and search.
    """
    categories = await service.list_categories(conn, limit, offset, search)
    
    for cat in categories:
        cat['subcategories'] = await service.get_subcategories(conn, cat['category_id'])
        
    return categories

@router.post("", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(
    category: CategoryCreate, 
    conn: Any = Depends(get_raw_db),
    service: CategoryDBService = Depends(get_category_service),
    industry_service: IndustryDBService = Depends(get_industry_service)
):
    """
    Create a new document category within an industry.
    """
    # Verify industry exists
    industry = await industry_service.get_industry(conn, category.industry_id)
    if not industry:
        raise HTTPException(status_code=404, detail=f"Industry with ID {category.industry_id} not found")

    new_category = await service.create_category(
        conn, category.industry_id, category.name, category.description
    )

    new_category['subcategories'] = []
    return new_category

@router.get("/{category_id}", response_model=CategoryResponse)
async def get_category(
    category_id: uuid.UUID, 
    conn: Any = Depends(get_raw_db),
    service: CategoryDBService = Depends(get_category_service)
):
    """
    Retrieve a specific category and its subcategories.
    """
    category = await service.get_category(conn, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    
    category['subcategories'] = await service.get_subcategories(conn, category_id)
    return category

@router.patch("/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: uuid.UUID, 
    category_update: CategoryUpdate, 
    conn: Any = Depends(get_raw_db),
    service: CategoryDBService = Depends(get_category_service),
    industry_service: IndustryDBService = Depends(get_industry_service)
):
    """
    Update category details.
    """
    existing = await service.get_category(conn, category_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Category not found")
    
    update_data = category_update.model_dump(exclude_unset=True)
    
    if "industry_id" in update_data:
        industry = await industry_service.get_industry(conn, update_data["industry_id"])
        if not industry:
            raise HTTPException(status_code=404, detail=f"Industry with ID {update_data['industry_id']} not found")

    updated_category = await service.update_category(conn, category_id, update_data)
    updated_category['subcategories'] = await service.get_subcategories(conn, category_id)
    
    return updated_category

@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: uuid.UUID, 
    conn: Any = Depends(get_raw_db),
    service: CategoryDBService = Depends(get_category_service)
):
    """
    Delete a category.
    """
    deleted = await service.delete_category(conn, category_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Category not found")
    return None
