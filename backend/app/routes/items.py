from decimal import Decimal
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.dependencies.auth import (
    get_current_user, get_current_active_student, get_optional_current_user
)
from backend.app.models.user import AppUser
from backend.app.schemas.item import (
    ItemCreate, ItemUpdate, ItemOut, ItemDetailOut, CategoryOut, PickupLocationOut
)
from backend.app.services.item_service import (
    get_categories, get_pickup_locations, create_item, update_item,
    archive_item, search_items, get_item_details, get_item_availability,
    toggle_favorite, get_user_listings
)

router = APIRouter(prefix="/items", tags=["Item Listings"])


@router.get("/categories", response_model=List[CategoryOut])
def list_categories(db: Session = Depends(get_db)):
    return get_categories(db)


@router.get("/locations", response_model=List[PickupLocationOut])
def list_locations(db: Session = Depends(get_db)):
    return get_pickup_locations(db)


@router.get("", response_model=Dict[str, Any])
def explore_items(
    q: Optional[str] = None,
    category_id: Optional[int] = None,
    location_id: Optional[int] = None,
    min_fee: Optional[Decimal] = None,
    max_fee: Optional[Decimal] = None,
    condition: Optional[str] = None,
    sort_by: str = Query("newest", pattern="^(newest|price_asc|price_desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: Optional[AppUser] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    items, total = search_items(
        db, current_user=current_user, q=q, category_id=category_id,
        location_id=location_id, min_fee=min_fee, max_fee=max_fee,
        condition=condition, sort_by=sort_by, page=page, page_size=page_size
    )
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total > 0 else 0
    }


@router.post("", response_model=ItemDetailOut, status_code=status.HTTP_201_CREATED)
def list_item(
    data: ItemCreate,
    current_user: AppUser = Depends(get_current_active_student),
    db: Session = Depends(get_db)
):
    item = create_item(db, current_user, data)
    return get_item_details(db, item.item_id, current_user)


@router.get("/my-listings", response_model=List[ItemOut])
def my_listings(
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return get_user_listings(db, current_user.user_id)


@router.get("/{item_id}", response_model=ItemDetailOut)
def get_item(
    item_id: int,
    current_user: Optional[AppUser] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    return get_item_details(db, item_id, current_user)


@router.put("/{item_id}", response_model=ItemDetailOut)
def edit_item(
    item_id: int,
    data: ItemUpdate,
    current_user: AppUser = Depends(get_current_active_student),
    db: Session = Depends(get_db)
):
    item = update_item(db, item_id, current_user, data)
    return get_item_details(db, item.item_id, current_user)


@router.delete("/{item_id}")
def delete_item(
    item_id: int,
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    archive_item(db, item_id, current_user)
    return {"message": "Listing archived successfully."}


@router.get("/{item_id}/availability")
def item_availability(item_id: int, db: Session = Depends(get_db)):
    return get_item_availability(db, item_id)


@router.post("/{item_id}/favorite")
def favorite_item(
    item_id: int,
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    is_fav = toggle_favorite(db, current_user.user_id, item_id)
    return {"item_id": item_id, "is_favorite": is_fav}
