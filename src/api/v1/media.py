"""
Media upload endpoints
"""
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from datetime import datetime
from src.models.responses import MediaUploadResponse
from src.services.storage_service import storage_service
from src.auth.jwt_auth import get_current_user, CurrentUser
from loguru import logger

router = APIRouter(prefix="/api/v1/media", tags=["Media"])


@router.post("/upload", response_model=MediaUploadResponse)
async def upload_media(
    file: UploadFile = File(...),
    type: str = Form(..., regex="^(image|audio)$"),
    current_user: CurrentUser = Depends(get_current_user)
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
        raise HTTPException(status_code=500, detail=f"File upload failed: {str(e)}")
    
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


