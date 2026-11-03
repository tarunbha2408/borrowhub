import os
import uuid
import shutil
from typing import Optional
from fastapi import UploadFile, HTTPException, status
from backend.app.core.config import settings

# Allowed MIME types and extensions
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

# Magic bytes of the accepted formats. The client-supplied Content-Type header
# is only a hint: without this check a file called ``photo.jpg`` could really be
# an HTML/SVG document served back from /uploads (stored-XSS vector).
MAGIC_SIGNATURES = (
    (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", ".png"),
    (b"GIF87a", "image/gif", ".gif"),
    (b"GIF89a", "image/gif", ".gif"),
    (b"RIFF", "image/webp", ".webp"),   # RIFF....WEBP, verified below
)


def sniff_image_type(contents: bytes) -> Optional[tuple]:
    """Return ``(mime, extension)`` detected from the file body, or ``None``."""
    for signature, mime, extension in MAGIC_SIGNATURES:
        if contents.startswith(signature):
            if mime == "image/webp" and contents[8:12] != b"WEBP":
                continue
            return mime, extension
    return None


def is_cloudinary_configured() -> bool:
    return bool(
        settings.CLOUDINARY_CLOUD_NAME and
        settings.CLOUDINARY_API_KEY and
        settings.CLOUDINARY_API_SECRET
    )


async def upload_image(file: UploadFile) -> str:
    """
    Validate and upload an image.
    Uses Cloudinary if configured; otherwise safely saves to static uploads folder.
    Returns the public image URL.
    """
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid image type '{file.content_type}'. Supported: JPEG, PNG, WebP, GIF."
        )

    # Read file content and check size
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The uploaded file is empty.")
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File size exceeds the 5MB limit."
        )

    # The declared type and the real bytes have to agree.
    sniffed = sniff_image_type(contents)
    if not sniffed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The file is not a real JPEG, PNG, WebP or GIF image.",
        )
    detected_mime, detected_ext = sniffed
    if detected_mime != file.content_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File content is {detected_mime}, which does not match the declared {file.content_type}.",
        )

    if is_cloudinary_configured():
        import cloudinary
        import cloudinary.uploader
        cloudinary.config(
            cloud_name=settings.CLOUDINARY_CLOUD_NAME,
            api_key=settings.CLOUDINARY_API_KEY,
            api_secret=settings.CLOUDINARY_API_SECRET,
            secure=True,
        )
        try:
            result = cloudinary.uploader.upload(
                contents,
                folder="borrowhub/items",
                resource_type="image",
            )
            return result.get("secure_url", result.get("url"))
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Cloudinary upload failed: {str(e)}"
            )
    else:
        # Local upload storage fallback
        static_dir = settings.UPLOAD_DIR
        os.makedirs(static_dir, exist_ok=True)
        # Extension comes from the sniffed bytes, never from the filename, so
        # an odd upload cannot land as .html/.svg under /uploads.
        ext = detected_ext

        unique_name = f"{uuid.uuid4().hex}{ext}"
        target_path = os.path.join(static_dir, unique_name)

        with open(target_path, "wb") as f:
            f.write(contents)

        return f"/uploads/{unique_name}"
