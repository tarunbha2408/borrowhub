from datetime import datetime, date, timezone
from decimal import Decimal
from typing import Optional, List, Dict, Any, Tuple
from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, and_, desc, asc, func
from backend.app.models.catalog import Category, PickupLocation, Item, ItemImage, Favorite
from backend.app.models.borrow import BookedDate
from backend.app.models.trust import Review
from backend.app.models.user import AppUser
from backend.app.schemas.item import ItemCreate, ItemUpdate, ItemOut, ItemDetailOut, ItemImageOut


def get_categories(db: Session) -> List[Category]:
    return db.query(Category).order_by(Category.category_id).all()


def get_pickup_locations(db: Session) -> List[PickupLocation]:
    return db.query(PickupLocation).order_by(PickupLocation.location_id).all()


def create_item(db: Session, owner: AppUser, data: ItemCreate) -> Item:
    # Resolve location
    location_id = data.location_id
    if not location_id and data.custom_location:
        loc = db.query(PickupLocation).filter(
            PickupLocation.name == data.custom_location.strip()
        ).first()
        if not loc:
            loc = PickupLocation(name=data.custom_location.strip(), description="Custom campus pickup point")
            db.add(loc)
            db.flush()
        location_id = loc.location_id

    if not location_id:
        first_loc = db.query(PickupLocation).first()
        if first_loc:
            location_id = first_loc.location_id

    # Verify category exists
    cat = db.query(Category).filter(Category.category_id == data.category_id).first()
    if not cat:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid category ID.")

    item = Item(
        owner_id=owner.user_id,
        category_id=data.category_id,
        location_id=location_id,
        title=data.title.strip(),
        description=data.description.strip() if data.description else None,
        item_condition=data.item_condition,
        deposit_amount=data.deposit_amount,
        daily_fee=data.daily_fee,
        max_borrow_days=data.max_borrow_days,
        listing_status="ACTIVE",
    )
    db.add(item)
    db.flush()

    # Add images (max 5)
    for idx, url in enumerate(data.image_urls[:5]):
        img = ItemImage(
            item_id=item.item_id,
            image_url=url.strip(),
            sort_order=idx,
            is_primary=1 if idx == 0 else 0,
        )
        db.add(img)

    db.commit()
    db.refresh(item)
    return item


def update_item(db: Session, item_id: int, user: AppUser, data: ItemUpdate) -> Item:
    item = db.query(Item).filter(
        Item.item_id == item_id,
        Item.deleted_at.is_(None)
    ).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found.")

    if item.owner_id != user.user_id and user.role not in ("ADMIN", "MODERATOR"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to edit this listing."
        )

    if data.title is not None:
        item.title = data.title.strip()
    if data.category_id is not None:
        item.category_id = data.category_id
    if data.location_id is not None:
        item.location_id = data.location_id
    elif data.custom_location is not None:
        loc = db.query(PickupLocation).filter(
            PickupLocation.name == data.custom_location.strip()
        ).first()
        if not loc:
            loc = PickupLocation(name=data.custom_location.strip(), description="Custom campus pickup point")
            db.add(loc)
            db.flush()
        item.location_id = loc.location_id

    if data.description is not None:
        item.description = data.description.strip()
    if data.item_condition is not None:
        item.item_condition = data.item_condition
    if data.deposit_amount is not None:
        item.deposit_amount = data.deposit_amount
    if data.daily_fee is not None:
        item.daily_fee = data.daily_fee
    if data.max_borrow_days is not None:
        item.max_borrow_days = data.max_borrow_days
    if data.listing_status is not None:
        item.listing_status = data.listing_status

    if data.image_urls is not None:
        # Replace images
        db.query(ItemImage).filter(ItemImage.item_id == item_id).delete()
        for idx, url in enumerate(data.image_urls[:5]):
            img = ItemImage(
                item_id=item_id,
                image_url=url.strip(),
                sort_order=idx,
                is_primary=1 if idx == 0 else 0,
            )
            db.add(img)

    db.commit()
    db.refresh(item)
    return item


def archive_item(db: Session, item_id: int, user: AppUser) -> bool:
    item = db.query(Item).filter(
        Item.item_id == item_id,
        Item.deleted_at.is_(None)
    ).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found.")

    if item.owner_id != user.user_id and user.role not in ("ADMIN", "MODERATOR"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to archive this listing."
        )

    item.listing_status = "ARCHIVED"
    item.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return True


def search_items(
    db: Session,
    current_user: Optional[AppUser] = None,
    q: Optional[str] = None,
    category_id: Optional[int] = None,
    location_id: Optional[int] = None,
    min_fee: Optional[Decimal] = None,
    max_fee: Optional[Decimal] = None,
    condition: Optional[str] = None,
    sort_by: str = "newest",
    page: int = 1,
    page_size: int = 20,
) -> Tuple[List[ItemOut], int]:
    query = db.query(Item).options(
        joinedload(Item.owner),
        joinedload(Item.category),
        joinedload(Item.location),
        joinedload(Item.images),
    ).filter(
        Item.listing_status == "ACTIVE",
        Item.deleted_at.is_(None)
    )

    if q:
        search_pattern = f"%{q.strip()}%"
        query = query.filter(
            or_(
                Item.title.ilike(search_pattern),
                Item.description.ilike(search_pattern)
            )
        )

    if category_id:
        query = query.filter(Item.category_id == category_id)

    if location_id:
        query = query.filter(Item.location_id == location_id)

    if min_fee is not None:
        query = query.filter(Item.daily_fee >= min_fee)

    if max_fee is not None:
        query = query.filter(Item.daily_fee <= max_fee)

    if condition:
        query = query.filter(Item.item_condition == condition)

    total_count = query.count()

    # Sorting
    if sort_by == "price_asc":
        query = query.order_by(asc(Item.daily_fee))
    elif sort_by == "price_desc":
        query = query.order_by(desc(Item.daily_fee))
    else:  # newest
        query = query.order_by(desc(Item.created_at))

    # Pagination
    offset = (page - 1) * page_size
    items = query.offset(offset).limit(page_size).all()

    # Check favorites for logged in user
    fav_set = set()
    if current_user:
        fav_rows = db.query(Favorite.item_id).filter(Favorite.user_id == current_user.user_id).all()
        fav_set = {r[0] for r in fav_rows}

    results = []
    for it in items:
        primary_img = None
        for img in it.images:
            if img.is_primary:
                primary_img = img.image_url
                break
        if not primary_img and it.images:
            primary_img = it.images[0].image_url

        results.append(ItemOut(
            item_id=it.item_id,
            owner_id=it.owner_id,
            owner_name=it.owner.full_name if it.owner else "Student",
            owner_email=it.owner.svnit_email if it.owner else "",
            owner_hostel=it.owner.hostel_or_dept if it.owner else None,
            category_id=it.category_id,
            category_name=it.category.category_name if it.category else "",
            location_id=it.location_id,
            location_name=it.location.name if it.location else "SVNIT Campus",
            title=it.title,
            description=it.description,
            item_condition=it.item_condition,
            deposit_amount=it.deposit_amount,
            daily_fee=it.daily_fee,
            max_borrow_days=it.max_borrow_days,
            listing_status=it.listing_status,
            primary_image_url=primary_img,
            is_favorite=(it.item_id in fav_set),
            created_at=it.created_at,
        ))

    return results, total_count


def get_item_details(db: Session, item_id: int, current_user: Optional[AppUser] = None) -> ItemDetailOut:
    it = db.query(Item).options(
        joinedload(Item.owner),
        joinedload(Item.category),
        joinedload(Item.location),
        joinedload(Item.images),
    ).filter(
        Item.item_id == item_id,
        Item.deleted_at.is_(None)
    ).first()

    if not it:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found.")

    is_fav = False
    if current_user:
        is_fav = bool(db.query(Favorite).filter(
            Favorite.user_id == current_user.user_id,
            Favorite.item_id == item_id
        ).first())

    primary_img = None
    images_out = []
    for img in sorted(it.images, key=lambda x: x.sort_order):
        if img.is_primary:
            primary_img = img.image_url
        images_out.append(ItemImageOut(
            image_id=img.image_id,
            image_url=img.image_url,
            sort_order=img.sort_order,
            is_primary=img.is_primary,
        ))
    if not primary_img and images_out:
        primary_img = images_out[0].image_url

    # Calculate average rating for owner
    avg_rating = db.query(func.avg(Review.rating)).filter(Review.reviewee_id == it.owner_id).scalar()
    review_count = db.query(func.count(Review.review_id)).filter(Review.reviewee_id == it.owner_id).scalar() or 0

    return ItemDetailOut(
        item_id=it.item_id,
        owner_id=it.owner_id,
        owner_name=it.owner.full_name if it.owner else "Student",
        owner_email=it.owner.svnit_email if it.owner else "",
        owner_hostel=it.owner.hostel_or_dept if it.owner else None,
        category_id=it.category_id,
        category_name=it.category.category_name if it.category else "",
        location_id=it.location_id,
        location_name=it.location.name if it.location else "SVNIT Campus",
        title=it.title,
        description=it.description,
        item_condition=it.item_condition,
        deposit_amount=it.deposit_amount,
        daily_fee=it.daily_fee,
        max_borrow_days=it.max_borrow_days,
        listing_status=it.listing_status,
        primary_image_url=primary_img,
        is_favorite=is_fav,
        created_at=it.created_at,
        images=images_out,
        average_rating=round(float(avg_rating), 1) if avg_rating else None,
        reviews_count=review_count,
    )


def get_item_availability(db: Session, item_id: int) -> Dict[str, Any]:
    today = date.today()
    booked = db.query(BookedDate.booked_date).filter(
        BookedDate.item_id == item_id,
        BookedDate.booked_date >= today
    ).order_by(BookedDate.booked_date).all()

    dates = [row[0].isoformat() for row in booked]
    return {
        "item_id": item_id,
        "booked_dates": dates,
        "is_available_today": (today.isoformat() not in dates)
    }


def toggle_favorite(db: Session, user_id: int, item_id: int) -> bool:
    fav = db.query(Favorite).filter(
        Favorite.user_id == user_id,
        Favorite.item_id == item_id
    ).first()
    if fav:
        db.delete(fav)
        db.commit()
        return False
    else:
        new_fav = Favorite(user_id=user_id, item_id=item_id)
        db.add(new_fav)
        db.commit()
        return True


def get_user_listings(db: Session, user_id: int) -> List[ItemOut]:
    items = db.query(Item).options(
        joinedload(Item.owner),
        joinedload(Item.category),
        joinedload(Item.location),
        joinedload(Item.images),
    ).filter(
        Item.owner_id == user_id,
        Item.deleted_at.is_(None)
    ).order_by(desc(Item.created_at)).all()

    results = []
    for it in items:
        primary_img = None
        for img in it.images:
            if img.is_primary:
                primary_img = img.image_url
                break
        if not primary_img and it.images:
            primary_img = it.images[0].image_url

        results.append(ItemOut(
            item_id=it.item_id,
            owner_id=it.owner_id,
            owner_name=it.owner.full_name if it.owner else "Student",
            owner_email=it.owner.svnit_email if it.owner else "",
            owner_hostel=it.owner.hostel_or_dept if it.owner else None,
            category_id=it.category_id,
            category_name=it.category.category_name if it.category else "",
            location_id=it.location_id,
            location_name=it.location.name if it.location else "SVNIT Campus",
            title=it.title,
            description=it.description,
            item_condition=it.item_condition,
            deposit_amount=it.deposit_amount,
            daily_fee=it.daily_fee,
            max_borrow_days=it.max_borrow_days,
            listing_status=it.listing_status,
            primary_image_url=primary_img,
            is_favorite=False,
            created_at=it.created_at,
        ))
    return results
