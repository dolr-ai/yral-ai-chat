"""
Chat endpoints
"""

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response, WebSocket, WebSocketDisconnect
from fastapi.security import HTTPBearer

from src.auth.jwt_auth import CurrentUser, get_current_user, get_current_user_ws
from src.core.background_tasks import (
    invalidate_cache_for_user,
    log_ai_usage,
    update_conversation_stats,
)
from src.core.dependencies import ChatServiceDep, MessageRepositoryDep, StorageServiceDep
from src.core.websocket import manager
from src.models.entities import InfluencerStatus, Message
from src.models.internal import SendMessageParams
from src.models.requests import CreateConversationRequest, GenerateImageRequest, SendMessageRequest
from src.models.responses import (
    ConversationResponse,
    DeleteConversationResponse,
    InfluencerBasicInfo,
    ListConversationsResponse,
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
    if msg.media_urls:
        for url in msg.media_urls:
            key = storage_service.extract_key_from_url(url)
            presigned_media_urls.append(presigned_urls.get(key, url) if presigned_urls else url)

    audio_url = msg.audio_url
    if audio_url:
        key = storage_service.extract_key_from_url(audio_url)
        audio_url = presigned_urls.get(key, audio_url) if presigned_urls else audio_url

    return MessageResponse(
        id=msg.id, role=msg.role, content=msg.content,
        message_type=msg.message_type, media_urls=presigned_media_urls,
        audio_url=audio_url, audio_duration_seconds=msg.audio_duration_seconds,
        token_count=msg.token_count, created_at=msg.created_at,
        status=msg.status, is_read=msg.is_read,
    )


async def _convert_messages(
    messages: list[Message],
    storage_service: StorageService,
    sort_newest: bool = True
) -> list[MessageResponse]:
    """Helper to batch convert messages with presigned URLs"""
    if not messages:
        return []
        
    presigned_map = await storage_service.get_presigned_urls_for_messages(messages)
    
    if sort_newest:
        messages = sorted(messages, key=lambda m: m.created_at, reverse=True)
        
    return [await _convert_message_to_response(m, storage_service, presigned_map) for m in messages]


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

    recent_messages = await _convert_messages(conversation.recent_messages, storage_service) if conversation.recent_messages else []

    return ConversationResponse(
        id=conversation.id,
        user_id=conversation.user_id,
        influencer_id=conversation.influencer.id,
        influencer=InfluencerBasicInfo(
            id=conversation.influencer.id,
            name=conversation.influencer.name,
            display_name=conversation.influencer.display_name,
            avatar_url=conversation.influencer.avatar_url,
            suggested_messages=conversation.influencer.suggested_messages,
            is_online=conversation.influencer.is_active == InfluencerStatus.ACTIVE,
        ),
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        message_count=conversation.message_count or 0,
        last_message=recent_messages[0] if recent_messages else None,
        recent_messages=recent_messages,
    )


@router.get(
    "/conversations",
    response_model=ListConversationsResponse,
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
    
    # Batch generate presigned URLs for all messages and avatars efficiently
    all_messages = []
    all_influencers = []
    for conv in conversations:
        if conv.recent_messages:
            all_messages.extend(conv.recent_messages)
        if conv.influencer:
            all_influencers.append(conv.influencer)
            
    # Combine everything for one single batch call to get all URLs needed
    presigned_map = await storage_service.generate_presigned_urls_batch(
        storage_service.collect_keys_from_messages(all_messages + all_influencers)
    )

    conversation_responses = []
    for conv in conversations:
        # Resolve influencer avatar URL using the map
        if conv.influencer and conv.influencer.avatar_url:
            key = storage_service.extract_key_from_url(conv.influencer.avatar_url)
            conv.influencer.avatar_url = presigned_map.get(key, conv.influencer.avatar_url)

        # Convert recent messages using the map
        recent_messages = [
            await _convert_message_to_response(msg, storage_service, presigned_map)
            for msg in (conv.recent_messages or [])
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
                    is_online=conv.influencer.is_active == InfluencerStatus.ACTIVE,
                ),
                created_at=conv.created_at,
                updated_at=conv.updated_at,
                message_count=conv.message_count or 0,
                last_message=recent_messages[0] if recent_messages else None,
                recent_messages=recent_messages,
            )
        )

    return ListConversationsResponse(
        conversations=conversation_responses,
        total=len(conversation_responses),
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

    message_responses = await _convert_messages(messages, storage_service, sort_newest=(order == "desc"))

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
    user_msg, assistant_msg, is_duplicate = await chat_service.send_message(
        SendMessageParams(
            conversation_id=conversation_id,
            user_id=current_user.user_id,
            content=request.content,
            message_type=request.message_type,
            media_urls=request.media_urls or [],
            audio_url=request.audio_url,
            audio_duration_seconds=request.audio_duration_seconds,
            background_tasks=background_tasks,
            client_message_id=request.client_message_id,
        )
    )

    # Handle status code for errors
    if assistant_msg.content == ChatService.FALLBACK_ERROR_MESSAGE:
        response.status_code = 503

    # Log AI usage if needed
    if assistant_msg.token_count and not is_duplicate:
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

    # Convert messages for response
    # We use a batch convert for user and assistant message together
    res_user, res_assistant = await _convert_messages([user_msg, assistant_msg], storage_service, sort_newest=False)

    return SendMessageResponse(
        user_message=res_user,
        assistant_message=res_assistant,
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
        res = await _convert_messages([message], storage_service)
        return res[0]
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
    current_user: CurrentUser = Depends(get_current_user_ws),  # noqa: B008
):
    """
    WebSocket endpoint for real-time inbox updates.
    
    ### Connection:
    `ws://{host}/api/v1/chat/ws/inbox/{user_id}?token={jwt_token}`
    
    ### Events:
    Clients connect to receive real-time events:
    - `new_message`: When a new message arrives in any conversation
    - `conversation_read`: When a conversation is marked as read
    - `typing_status`: When an influencer is typing
    """
    # Verify user_id matches token subject
    if current_user.user_id != user_id:
        await websocket.close(code=4003)  # Forbidden
        return

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
    operation_id="docWebSocketEvents",
    tags=["Documentation"],
)
async def doc_websocket_events():
    """Dummy endpoint for WebSocket documentation"""
    return Response(status_code=418)  # I'm a teapot

