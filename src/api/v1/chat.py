"""
Chat endpoints
"""

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response, WebSocket, WebSocketDisconnect
from fastapi.security import HTTPBearer

from src.auth.jwt_auth import CurrentUser, get_current_user
from src.core.background_tasks import (
    invalidate_cache_for_user,
    log_ai_usage,
    update_conversation_stats,
)
from src.core.dependencies import ChatServiceDep, MessageRepositoryDep, StorageServiceDep
from src.core.websocket import manager
from src.models.entities import Message
from src.models.internal import SendMessageParams
from src.models.requests import CreateConversationRequest, GenerateImageRequest, SendMessageRequest
from src.models.responses import (
    ConversationResponse,
    DeleteConversationResponse,
    InfluencerBasicInfo,
    ListMessagesResponse,
    MarkConversationAsReadResponse,
    MessageResponse,
    SendMessageResponse,
)
from src.models.websocket_events import WebSocketEvent
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
        status=msg.status,
        is_read=msg.is_read,
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

    return ConversationResponse(
        id=conversation.id,
        user_id=conversation.user_id,
        influencer_id=conversation.influencer.id,
        influencer=InfluencerBasicInfo(
            id=conversation.influencer.id,
            display_name=conversation.influencer.display_name,
            avatar_url=conversation.influencer.avatar_url,
            is_online=True,
        ),
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        unread_count=0,
        last_message=None,
    )


@router.get(
    "/conversations",
    response_model=list[ConversationResponse],
    operation_id="listConversations",
    summary="List user conversations",
    description="Retrieve list of user's conversations, optionally filtered by influencer.",
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
    conversations, _total = await chat_service.list_conversations(
        user_id=current_user.user_id,
        influencer_id=influencer_id,
        limit=limit,
        offset=offset,
    )

    conversation_responses: list[ConversationResponse] = []
    
    for conv in conversations:
        conversation_responses.append(
            ConversationResponse(
                id=conv.id,
                user_id=conv.user_id,
                influencer_id=conv.influencer.id,
                influencer=InfluencerBasicInfo(
                    id=conv.influencer.id,
                    display_name=conv.influencer.display_name,
                    avatar_url=conv.influencer.avatar_url,
                    is_online=True,  # Defaulting to True as requested in schema
                ),
                created_at=conv.created_at,
                updated_at=conv.updated_at,
                unread_count=conv.unread_count,
                last_message=conv.last_message,
            )
        )

    return conversation_responses


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
        SendMessageParams(
            conversation_id=conversation_id,
            user_id=current_user.user_id,
            content=request.content,
            message_type=request.message_type,
            media_urls=request.media_urls or [],
            audio_url=request.audio_url,
            audio_duration_seconds=request.audio_duration_seconds,
            background_tasks=background_tasks,
        )
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


@router.post(
    "/conversations/{conversation_id}/images",
    response_model=MessageResponse,
    operation_id="generateImage",
    summary="Generate an image in conversation",
    description="""
    Generate an image based on a prompt or conversation context.
    
    If 'prompt' is provided, it is used directly.
    If 'prompt' is omitted, the last few messages are used to generate a relevant image prompt.
    The generated image is saved to storage and returned as a new message.
    """,
    responses={
        201: {"description": "Image generated successfully"},
        401: {"description": "Unauthorized"},
        403: {"description": "Forbidden - Not your conversation"},
        404: {"description": "Conversation not found"},
        500: {"description": "Internal server error"},
        503: {"description": "Image generation service unavailable"},
    },
    status_code=201,
)
async def generate_image(
    conversation_id: str,
    request: GenerateImageRequest,
    current_user: CurrentUser = Depends(get_current_user),  # noqa: B008
    chat_service: ChatServiceDep = None,
    storage_service: StorageServiceDep = None,
):
    """Generate an image in the conversation"""
    try:
        message = await chat_service.generate_image_for_conversation(
            conversation_id=conversation_id,
            user_id=current_user.user_id,
            prompt=request.prompt,
        )
        return await _convert_message_to_response(message, storage_service)
    except NotImplementedError:
        # 503 if service not configured
        return Response(status_code=503, content="Image generation service unavailable")


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


@router.post(
    "/conversations/{conversation_id}/read",
    response_model=MarkConversationAsReadResponse,
    operation_id="markConversationAsRead",
    summary="Mark conversation as read",
    description="Mark all messages in a conversation as read and reset unread count to 0",
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
    result = await chat_service.mark_conversation_as_read(
        conversation_id=conversation_id,
        user_id=current_user.user_id,
    )

    return MarkConversationAsReadResponse(**result)


@router.websocket("/ws/inbox/{user_id}")
async def websocket_inbox_endpoint(
    websocket: WebSocket,
    user_id: str,
):
    """
    WebSocket endpoint for real-time inbox updates.
    
    ### Connection:
    `ws://{host}/api/v1/chat/ws/inbox/{user_id}`
    
    ### Events:
    Clients connect to receive real-time events:
    - `new_message`: When a new message arrives in any conversation
    - `conversation_read`: When a conversation is marked as read
    - `typing_status`: When an influencer is typing
    """
    await manager.connect(websocket, user_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)


@router.get(
    "/ws/docs",
    response_model=WebSocketEvent,
    include_in_schema=True,
    summary="WebSocket Event Schemas (Documentation Only)",
    description="This endpoint does not perform any action. It exists solely to expose the Pydantic models for WebSocket events to the OpenAPI (Swagger) documentation.",
    tags=["Documentation"],
)
async def doc_websocket_events():
    """Dummy endpoint for WebSocket documentation"""
    return Response(status_code=418)  # I'm a teapot

