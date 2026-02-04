"""
Chat endpoints
"""
from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response
from fastapi.security import HTTPBearer

from src.auth.jwt_auth import CurrentUser, get_current_user
from src.core.background_tasks import (
    invalidate_cache_for_user,
    log_ai_usage,
    update_conversation_stats,
)
from src.core.dependencies import ChatServiceDep, MessageRepositoryDep, StorageServiceDep
from src.models.entities import Message
from src.models.requests import CreateConversationRequest, SendMessageRequest
from src.models.responses import (
    ConversationResponse,
    DeleteConversationResponse,
    InfluencerBasicInfo,
    ListConversationsResponse,
    ListMessagesResponse,
    MessageResponse,
    SendMessageResponse,
)
from src.services.chat_service import ChatService
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
    )


@router.post(
    "/conversations",
    response_model=ConversationResponse,
    response_model_exclude_none=True,
    status_code=201,
    operation_id="createConversation",
    summary="Create a new conversation",
    description="""
    Create a new conversation with an AI influencer.
    
    If a conversation already exists between the user and influencer,
    returns the existing conversation instead of creating a new one.
    
    **Response includes:**
    - `recent_messages` array containing the last 10 messages (newest first) when message_count >= 1
    - For new conversations, the greeting message (if any) is included in `recent_messages`
    
    **Authentication required**: JWT token in Authorization header
    """,
    responses={
        201: {
            "description": "Conversation created successfully",
            "content": {
                "application/json": {
                    "example": {
                        "id": "550e8400-e29b-41d4-a716-446655440000",
                        "user_id": "user123",
                        "influencer": {
                            "id": "660e8400-e29b-41d4-a716-446655440000",
                            "name": "tech_guru",
                            "display_name": "Tech Guru AI",
                            "avatar_url": "https://example.com/avatar.jpg",
                        },
                        "created_at": "2024-01-15T10:30:00Z",
                        "updated_at": "2024-01-15T10:30:00Z",
                        "message_count": 0,
                    }
                }
            },
        },
        400: {"description": "Bad request - Invalid influencer_id format"},
        401: {"description": "Unauthorized - Invalid or missing JWT token"},
        404: {"description": "Influencer not found"},
        422: {"description": "Validation error - Request body validation failed"},
        429: {"description": "Rate limit exceeded"},
        500: {"description": "Internal server error"},
    },
)
async def create_conversation(
    request: CreateConversationRequest,
    current_user: CurrentUser = Depends(get_current_user),  # noqa: B008
    chat_service: ChatServiceDep = None,
    message_repo: MessageRepositoryDep = None,
    storage_service: StorageServiceDep = None,
):
    """Create a new conversation with an AI influencer"""
    conversation, _is_new = await chat_service.create_conversation(
        user_id=current_user.user_id,
        influencer_id=request.influencer_id,
    )

    message_count = await message_repo.count_by_conversation(conversation.id)
    
    recent_messages: list[MessageResponse] | None = None
    if message_count >= 1:
        recent_messages_list = await message_repo.list_by_conversation(
            conversation_id=conversation.id,
            limit=10,
            offset=0,
            order="desc",
        )
        if recent_messages_list:
            recent_messages = [
                await _convert_message_to_response(msg, storage_service)
                for msg in recent_messages_list
            ]

    return ConversationResponse(
        id=conversation.id,
        user_id=conversation.user_id,
        influencer=InfluencerBasicInfo(
            id=conversation.influencer.id,
            name=conversation.influencer.name,
            display_name=conversation.influencer.display_name,
            avatar_url=conversation.influencer.avatar_url,
            suggested_messages=conversation.influencer.suggested_messages
            if message_count <= 1
            else None,
        ),
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        message_count=message_count,
        recent_messages=recent_messages,
    )

@router.get(
    "/conversations",
    response_model=ListConversationsResponse,
    operation_id="listConversations",
    summary="List user conversations",
    description="Retrieve paginated list of user's conversations, optionally filtered by influencer. Includes the last 10 messages per conversation.",
    responses={
        200: {"description": "List of conversations retrieved successfully"},
        401: {"description": "Unauthorized - Invalid or missing JWT token"},
        422: {"description": "Validation error - Invalid query parameters"},
        429: {"description": "Rate limit exceeded"},
        500: {"description": "Internal server error"},
    },
)
async def list_conversations(
    limit: int = Query(default=20, ge=1, le=100, description="Number of conversations to return"),
    offset: int = Query(default=0, ge=0, description="Number of conversations to skip"),
    influencer_id: str | None = Query(default=None, description="Filter by specific influencer ID"),
    current_user: CurrentUser = Depends(get_current_user),  # noqa: B008
    chat_service: ChatServiceDep = None,
    message_repo: MessageRepositoryDep = None,
    storage_service: StorageServiceDep = None,
):
    """
    List user's conversations
    
    Optionally filter by influencer_id
    """
    conversations, total = await chat_service.list_conversations(
        user_id=current_user.user_id,
        influencer_id=influencer_id,
        limit=limit,
        offset=offset,
    )

    conversation_responses: list[ConversationResponse] = []
    
    # Collect all messages that need URL signing
    all_messages_for_signing = []
    for conv in conversations:
        if conv.recent_messages:
            all_messages_for_signing.extend(conv.recent_messages)
            
    # Batch generate presigned URLs if StorageService is available
    presigned_map = {}
    if storage_service and all_messages_for_signing:
        all_keys = []
        for msg in all_messages_for_signing:
            if msg.media_urls:
                for url in msg.media_urls:
                    if url:
                        all_keys.append(storage_service.extract_key_from_url(url))
            if msg.audio_url:
                all_keys.append(storage_service.extract_key_from_url(msg.audio_url))
        
        if all_keys:
            presigned_map = await storage_service.generate_presigned_urls_batch(all_keys)

    for conv in conversations:
        recent_messages: list[MessageResponse] | None = None
        if conv.recent_messages:
            recent_messages = [
                await _convert_message_to_response(msg, storage_service, presigned_map)
                for msg in conv.recent_messages
            ]

        conversation_responses.append(
            ConversationResponse(
                id=conv.id,
                user_id=conv.user_id,
                influencer=InfluencerBasicInfo(
                    id=conv.influencer.id,
                    name=conv.influencer.name,
                    display_name=conv.influencer.display_name,
                    avatar_url=conv.influencer.avatar_url,
                    # Only show suggested messages if conversation is empty or has just 1 message (greeting)
                    suggested_messages=conv.influencer.suggested_messages
                    if (conv.message_count or 0) <= 1
                    else None,
                ),
                created_at=conv.created_at,
                updated_at=conv.updated_at,
                message_count=conv.message_count or 0,
                recent_messages=recent_messages,
            )
        )

    return ListConversationsResponse(
        conversations=conversation_responses,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=ListMessagesResponse,
    operation_id="listMessages",
    summary="Get conversation messages",
    description="Retrieve paginated message history for a conversation",
    responses={
        200: {"description": "Messages retrieved successfully"},
        401: {"description": "Unauthorized - Invalid or missing JWT token"},
        403: {"description": "Forbidden - Not authorized to access this conversation"},
        404: {"description": "Conversation not found"},
        422: {"description": "Validation error - Invalid parameters"},
        429: {"description": "Rate limit exceeded"},
        500: {"description": "Internal server error"},
    },
)
async def list_messages(
    conversation_id: str,
    limit: int = Query(default=50, ge=1, le=200, description="Number of messages to return"),
    offset: int = Query(default=0, ge=0, description="Number of messages to skip"),
    order: str = Query(default="desc", pattern="^(asc|desc)$", description="Sort order: 'asc' or 'desc'"),
    current_user: CurrentUser = Depends(get_current_user),  # noqa: B008
    chat_service: ChatServiceDep = None,
    storage_service: StorageServiceDep = None,
):
    """Get paginated conversation message history"""
    messages, total = await chat_service.list_messages(
        conversation_id=conversation_id,
        user_id=current_user.user_id,
        limit=limit,
        offset=offset,
        order=order,
    )

    # Batch generate presigned URLs to prevent N+1 S3 calls
    all_keys = []
    if storage_service:
        for msg in messages:
            # Collect media keys
            if msg.media_urls:
                for url in msg.media_urls:
                    if url:
                        all_keys.append(storage_service.extract_key_from_url(url))
            # Collect audio keys
            if msg.audio_url:
                all_keys.append(storage_service.extract_key_from_url(msg.audio_url))
            
    # Generate all URLs in one parallel batch operation
    presigned_map = {}
    if all_keys and storage_service:
        presigned_map = await storage_service.generate_presigned_urls_batch(all_keys)

    message_responses = [
        await _convert_message_to_response(msg, storage_service, presigned_map)
        for msg in messages
    ]

    return ListMessagesResponse(
        conversation_id=conversation_id,
        messages=message_responses,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=SendMessageResponse,
    operation_id="sendMessage",
    summary="Send a message",
    description="""
    Send a message to an AI influencer and receive a response.
    
    Supports multiple message types:
    - **TEXT**: Plain text messages
    - **IMAGE**: Image-only messages
    - **MULTIMODAL**: Text with images
    - **AUDIO**: Voice/audio messages
    
    The AI response is returned immediately. Background tasks handle logging and cache updates.
    """,
    responses={
        200: {"description": "Message sent and AI response received successfully"},
        400: {"description": "Bad request - Invalid message format or content"},
        401: {"description": "Unauthorized - Invalid or missing JWT token"},
        403: {"description": "Forbidden - Not authorized to access this conversation"},
        404: {"description": "Conversation not found"},
        422: {"description": "Validation error - Invalid message data"},
        429: {"description": "Rate limit exceeded"},
        500: {"description": "Internal server error"},
        503: {"description": "Service unavailable - AI service temporarily unavailable"},
    },
)
async def send_message(
    conversation_id: str,
    request: SendMessageRequest,
    background_tasks: BackgroundTasks,
    response: Response,
    current_user: CurrentUser = Depends(get_current_user),  # noqa: B008
    chat_service: ChatServiceDep = None,
    storage_service: StorageServiceDep = None,
):
    """
    Send a message to AI influencer
    
    Supports:
    - Text-only messages
    - Image-only messages
    - Text + Image messages (multimodal)
    - Audio/voice messages
    
    Background tasks are used for logging and cache invalidation.
    """
    user_msg, assistant_msg = await chat_service.send_message(
        conversation_id=conversation_id,
        user_id=current_user.user_id,
        content=request.content,
        message_type=request.message_type,
        media_urls=request.media_urls or [],
        audio_url=request.audio_url,
        audio_duration_seconds=request.audio_duration_seconds,
        background_tasks=background_tasks,
    )

    # Check if we hit the fallback error message
    if assistant_msg.content == ChatService.FALLBACK_ERROR_MESSAGE:
        response.status_code = 503

    if assistant_msg.token_count:
        background_tasks.add_task(
            log_ai_usage,
            model="gemini",
            tokens=assistant_msg.token_count,
            user_id=current_user.user_id,
            conversation_id=str(conversation_id),
        )

    background_tasks.add_task(
        update_conversation_stats,
        conversation_id=str(conversation_id),
    )

    background_tasks.add_task(
        invalidate_cache_for_user,
        user_id=current_user.user_id,
    )

    return SendMessageResponse(
        user_message=await _convert_message_to_response(user_msg, storage_service),
        assistant_message=await _convert_message_to_response(assistant_msg, storage_service),
    )


@router.delete(
    "/conversations/{conversation_id}",
    response_model=DeleteConversationResponse,
    operation_id="deleteConversation",
    summary="Delete a conversation",
    description="Permanently delete a conversation and all its associated messages",
    responses={
        200: {"description": "Conversation deleted successfully"},
        401: {"description": "Unauthorized - Invalid or missing JWT token"},
        403: {"description": "Forbidden - Not authorized to delete this conversation"},
        404: {"description": "Conversation not found"},
        429: {"description": "Rate limit exceeded"},
        500: {"description": "Internal server error"},
    },
)
async def delete_conversation(
    conversation_id: str,
    current_user: CurrentUser = Depends(get_current_user),  # noqa: B008
    chat_service: ChatServiceDep = None,
):
    """Delete a conversation and all associated messages"""
    deleted_messages = await chat_service.delete_conversation(
        conversation_id=conversation_id,
        user_id=current_user.user_id,
    )

    return DeleteConversationResponse(
        success=True,
        message="Conversation deleted successfully",
        deleted_conversation_id=conversation_id,
        deleted_messages_count=deleted_messages,
    )
