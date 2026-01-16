"""Media upload endpoints"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from loguru import logger

from src.auth.jwt_auth import CurrentUser, get_current_user
from src.core.dependencies import StorageServiceDep
from src.models.responses import MediaUploadResponse

router = APIRouter(prefix="/api/v1/media", tags=["Media"])


@router.post(
    "/upload",
    response_model=MediaUploadResponse,
    operation_id="uploadMedia",
    summary="Upload media file",
    description="""
    Upload an image or audio file to cloud storage.
    
    **Supported formats:**
    - Images: JPEG, PNG, GIF, WebP (max 10MB)
    - Audio: MP3, WAV, M4A (max 20MB, 5 minutes)

    Returns a short-lived presigned URL for immediate access and a stable storage_key
    that can be used later when sending chat messages.

    **Authentication required**: JWT token in Authorization header
    """,
    responses={
        200: {"description": "File uploaded successfully"},
        400: {"description": "Bad request - Invalid file type or size"},
        401: {"description": "Unauthorized - Invalid or missing JWT token"},
        413: {"description": "Payload too large - File exceeds size limit"},
        422: {"description": "Validation error - Invalid form data"},
        429: {"description": "Rate limit exceeded"},
        500: {"description": "Internal server error - Upload failed"},
        503: {"description": "Service unavailable - Storage service unavailable"},
    },
)
async def upload_media(
    file: UploadFile = File(..., description="File to upload"),  # noqa: B008
    media_type: str = Form(
        ..., alias="type", pattern="^(image|audio)$", description="Type of media: 'image' or 'audio'"
    ),
    current_user: CurrentUser = Depends(get_current_user),  # noqa: B008
    storage_service: StorageServiceDep = None,
):
    """
    Upload media file (image or audio) to cloud storage.

    Returns a presigned URL for immediate access and a stable storage_key.
    """
    if not file:
        raise HTTPException(status_code=400, detail="No file provided")

    file_content = await file.read()
    file_size = len(file_content)

    if media_type == "image":
        storage_service.validate_image(file.filename, file_size)
    elif media_type == "audio":
        storage_service.validate_audio(file.filename, file_size)
    else:
        raise HTTPException(status_code=400, detail="Invalid type. Must be 'image' or 'audio'")

    try:
        s3_key, mime_type, file_size = await storage_service.save_file(
            file_content=file_content, filename=file.filename, user_id=current_user.user_id
        )
    except Exception as e:
        logger.error(f"File upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"File upload failed: {e!s}") from e

    try:
        presigned_url = storage_service.generate_presigned_url(s3_key)
    except Exception as e:
        logger.error(f"Failed to generate presigned URL for {s3_key}: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate access URL for uploaded file") from e

    duration_seconds = None

    return MediaUploadResponse(
        url=presigned_url,
        storage_key=s3_key,
        type=media_type,
        size=file_size,
        mime_type=mime_type,
        duration_seconds=duration_seconds,
        uploaded_at=datetime.now(tz=UTC),
    )
