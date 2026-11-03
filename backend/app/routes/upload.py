from fastapi import APIRouter, Depends, UploadFile, File, status
from backend.app.dependencies.auth import get_current_active_student
from backend.app.models.user import AppUser
from backend.app.services.cloudinary_service import upload_image

router = APIRouter(prefix="/upload", tags=["Media Upload"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_listing_image(
    file: UploadFile = File(...),
    current_user: AppUser = Depends(get_current_active_student)
):
    url = await upload_image(file)
    return {"url": url, "filename": file.filename}
