"""
Chat endpoints
"""

from fastapi import APIRouter, Depends
from fastapi.security import HTTPBearer

from src.auth.jwt_auth import CurrentUser, get_current_user
from src.core.dependencies import ChatServiceDep
from src.models.entities import Message
from src.models.responses import (
    MessageResponse,
)
from src.services.storage_service import StorageService

security = HTTPBearer()
router = APIRouter(prefix="/api/v1/chat", tags=["Chat"])


async def _convert_message_to_response(
    msg: Message,
    storage_service: StorageService,
    presigned_urls: dict[str, str] | None = None
) -> MessageResponse:
    """Convert Message to MessageResponse with presigned URLs"""
    presigned_media_urls = []
    
    # Process media URLs
    if msg.media_urls:
        for media_key in msg.media_urls:
            if not media_key:
                continue
            
            s3_key = storage_service.extract_key_from_url(media_key)
            # Use batch-generated URL if available, otherwise generate on-demand
            if presigned_urls and s3_key in presigned_urls:
                presigned_media_urls.append(presigned_urls[s3_key])
            else:
                try:
                    presigned_media_urls.append(await storage_service.generate_presigned_url(s3_key))
                except Exception:
                    presigned_media_urls.append(media_key)

    presigned_audio_url = None
    if msg.audio_url:
        s3_key = storage_service.extract_key_from_url(msg.audio_url)
        if presigned_urls and s3_key in presigned_urls:
            presigned_audio_url = presigned_urls[s3_key]
        else:
            try:
                presigned_audio_url = await storage_service.generate_presigned_url(s3_key)
            except Exception:
                presigned_audio_url = msg.audio_url

    return MessageResponse(
        id=msg.id,
        role=msg.role,
        content=msg.content,
        message_type=msg.message_type,
        media_urls=presigned_media_urls,
        audio_url=presigned_audio_url,
        audio_duration_seconds=msg.audio_duration_seconds,
        token_count=msg.token_count,
        created_at=msg.created_at,
        status=msg.status,
        is_read=msg.is_read,
    )


# ... (existing endpoints remain the same until delete_conversation)


@router.post(
    "/conversations/{conversation_id}/read",
    operation_id="markConversationAsRead",
    summary="Mark conversation as read",
    description="""
    Mark all unread messages in a conversation as read.
    
    This updates the read status of all assistant messages in the conversation
    and returns the updated unread count (which will be 0).
    """,
    responses={
        200: {"description": "Conversation marked as read successfully"},
        401: {"description": "Unauthorized - Invalid or missing JWT token"},
        403: {"description": "Forbidden - Not authorized to access this conversation"},
        404: {"description": "Conversation not found"},
        429: {"description": "Rate limit exceeded"},
        500: {"description": "Internal server error"},
    },
)
async def mark_conversation_as_read(
    conversation_id: str,
    current_user: CurrentUser = Depends(get_current_user),  # noqa: B008
    chat_service: ChatServiceDep = None,
):
    """Mark all messages in a conversation as read"""
    return await chat_service.mark_conversation_as_read(
        conversation_id=conversation_id,
        user_id=current_user.user_id,
    )
