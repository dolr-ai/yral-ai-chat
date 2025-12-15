"""
Media upload endpoints
"""
from datetime import datetime

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
    
    Returns the public URL of the uploaded file.
    
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
        503: {"description": "Service unavailable - Storage service unavailable"}
    }
)
async def upload_media(
    file: UploadFile = File(..., description="File to upload"),
    type: str = Form(..., pattern="^(image|audio)$", description="Type of media: 'image' or 'audio'"),
    current_user: CurrentUser = Depends(get_current_user),
    storage_service: StorageServiceDep = None
):
    """
    Upload media file (image or audio)
    
    Args:
        file: File to upload
        type: Type of file ("image" or "audio")
    
    Returns:
        MediaUploadResponse with file URL and metadata
    """
    if not file:
        raise HTTPException(status_code=400, detail="No file provided")

    # Read file content
    file_content = await file.read()
    file_size = len(file_content)

    # Validate based on type
    if type == "image":
        storage_service.validate_image(file.filename, file_size)
    elif type == "audio":
        storage_service.validate_audio(file.filename, file_size)
    else:
        raise HTTPException(status_code=400, detail="Invalid type. Must be 'image' or 'audio'")

    # Save file
    try:
        file_url, mime_type, file_size = await storage_service.save_file(
            file_content=file_content,
            filename=file.filename,
            user_id=current_user.user_id
        )
    except Exception as e:
        logger.error(f"File upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"File upload failed: {e!s}") from e

    # Get audio duration if applicable (placeholder for now)
    duration_seconds = None
    if type == "audio":
        # TODO: Implement actual audio duration detection
        duration_seconds = None

    return MediaUploadResponse(
        url=file_url,
        type=type,
        size=file_size,
        mime_type=mime_type,
        duration_seconds=duration_seconds,
        uploaded_at=datetime.utcnow()
    )


