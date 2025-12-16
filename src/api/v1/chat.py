"""
Chat endpoints
"""
from fastapi import APIRouter, BackgroundTasks, Depends, Query
from fastapi.security import HTTPBearer

from src.auth.jwt_auth import CurrentUser, get_current_user
from src.core.dependencies import ChatServiceDep, MessageRepositoryDep
from src.models.requests import CreateConversationRequest, SendMessageRequest
from src.models.responses import (
    ConversationResponse,
    DeleteConversationResponse,
    InfluencerBasicInfo,
    LastMessageInfo,
    ListConversationsResponse,
    ListMessagesResponse,
    MessageResponse,
    SendMessageResponse,
)

security = HTTPBearer()
router = APIRouter(prefix="/api/v1/chat", tags=["Chat"])


@router.post(
    "/conversations",
    response_model=ConversationResponse,
    status_code=201,
    operation_id="createConversation",
    summary="Create a new conversation",
    description="""
    Create a new conversation with an AI influencer.
    
    If a conversation already exists between the user and influencer, 
    returns the existing conversation instead of creating a new one.
    
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
                            "avatar_url": "https://example.com/avatar.jpg"
                        },
                        "created_at": "2024-01-15T10:30:00Z",
                        "updated_at": "2024-01-15T10:30:00Z",
                        "message_count": 0
                    }
                }
            }
        },
        400: {"description": "Bad request - Invalid influencer_id format"},
        401: {"description": "Unauthorized - Invalid or missing JWT token"},
        404: {"description": "Influencer not found"},
        422: {"description": "Validation error - Request body validation failed"},
        429: {"description": "Rate limit exceeded"},
        500: {"description": "Internal server error"}
    }
)
async def create_conversation(
    request: CreateConversationRequest,
    current_user: CurrentUser = Depends(get_current_user),
    chat_service: ChatServiceDep = None,
    message_repo: MessageRepositoryDep = None
):
    """Create a new conversation with an AI influencer"""
    conversation = await chat_service.create_conversation(
        user_id=current_user.user_id,
        influencer_id=request.influencer_id
    )

    # Get message count
    message_count = await message_repo.count_by_conversation(conversation.id)

    return ConversationResponse(
        id=conversation.id,
        user_id=conversation.user_id,
        influencer=InfluencerBasicInfo(
            id=conversation.influencer.id,
            name=conversation.influencer.name,
            display_name=conversation.influencer.display_name,
            avatar_url=conversation.influencer.avatar_url
        ),
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        message_count=message_count
    )


@router.get(
    "/conversations",
    response_model=ListConversationsResponse,
    operation_id="listConversations",
    summary="List user conversations",
    description="Retrieve paginated list of user's conversations, optionally filtered by influencer",
    responses={
        200: {"description": "List of conversations retrieved successfully"},
        401: {"description": "Unauthorized - Invalid or missing JWT token"},
        422: {"description": "Validation error - Invalid query parameters"},
        429: {"description": "Rate limit exceeded"},
        500: {"description": "Internal server error"}
    }
)
async def list_conversations(
    limit: int = Query(default=20, ge=1, le=100, description="Number of conversations to return"),
    offset: int = Query(default=0, ge=0, description="Number of conversations to skip"),
    influencer_id: str | None = Query(default=None, description="Filter by specific influencer ID"),
    current_user: CurrentUser = Depends(get_current_user),
    chat_service: ChatServiceDep = None
):
    """
    List user's conversations
    
    Optionally filter by influencer_id
    """
    conversations, total = await chat_service.list_conversations(
        user_id=current_user.user_id,
        influencer_id=influencer_id,
        limit=limit,
        offset=offset
    )

    # Convert to response models
    conversation_responses = []
    for conv in conversations:
        last_msg = None
        if conv.last_message:
            last_msg = LastMessageInfo(
                content=conv.last_message.get("content"),
                role=conv.last_message.get("role"),
                created_at=conv.last_message.get("created_at")
            )

        conversation_responses.append(
            ConversationResponse(
                id=conv.id,
                user_id=conv.user_id,
                influencer=InfluencerBasicInfo(
                    id=conv.influencer.id,
                    name=conv.influencer.name,
                    display_name=conv.influencer.display_name,
                    avatar_url=conv.influencer.avatar_url
                ),
                created_at=conv.created_at,
                updated_at=conv.updated_at,
                message_count=conv.message_count or 0,
                last_message=last_msg
            )
        )

    return ListConversationsResponse(
        conversations=conversation_responses,
        total=total,
        limit=limit,
        offset=offset
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
        500: {"description": "Internal server error"}
    }
)
async def list_messages(
    conversation_id: str,
    limit: int = Query(default=50, ge=1, le=200, description="Number of messages to return"),
    offset: int = Query(default=0, ge=0, description="Number of messages to skip"),
    order: str = Query(default="desc", pattern="^(asc|desc)$", description="Sort order: 'asc' or 'desc'"),
    current_user: CurrentUser = Depends(get_current_user),
    chat_service: ChatServiceDep = None
):
    """
    Get conversation message history
    
    order: 'asc' for oldest first, 'desc' for newest first
    """
    messages, total = await chat_service.list_messages(
        conversation_id=conversation_id,
        user_id=current_user.user_id,
        limit=limit,
        offset=offset,
        order=order
    )

    # Convert to response models
    message_responses = [
        MessageResponse(
            id=msg.id,
            role=msg.role,
            content=msg.content,
            message_type=msg.message_type,
            media_urls=msg.media_urls,
            audio_url=msg.audio_url,
            audio_duration_seconds=msg.audio_duration_seconds,
            token_count=msg.token_count,
            created_at=msg.created_at
        )
        for msg in messages
    ]

    return ListMessagesResponse(
        conversation_id=conversation_id,
        messages=message_responses,
        total=total,
        limit=limit,
        offset=offset
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
        503: {"description": "Service unavailable - AI service temporarily unavailable"}
    }
)
async def send_message(
    conversation_id: str,
    request: SendMessageRequest,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(get_current_user),
    chat_service: ChatServiceDep = None
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
        audio_duration_seconds=request.audio_duration_seconds
    )

    # Add background tasks for non-critical operations
    from src.core.background_tasks import (
        invalidate_cache_for_user,
        log_ai_usage,
        update_conversation_stats,
    )

    if assistant_msg.token_count:
        background_tasks.add_task(
            log_ai_usage,
            model="gemini",
            tokens=assistant_msg.token_count,
            user_id=current_user.user_id,
            conversation_id=str(conversation_id)
        )

    background_tasks.add_task(
        update_conversation_stats,
        conversation_id=str(conversation_id)
    )

    background_tasks.add_task(
        invalidate_cache_for_user,
        user_id=current_user.user_id
    )

    return SendMessageResponse(
        user_message=MessageResponse(
            id=user_msg.id,
            role=user_msg.role,
            content=user_msg.content,
            message_type=user_msg.message_type,
            media_urls=user_msg.media_urls,
            audio_url=user_msg.audio_url,
            audio_duration_seconds=user_msg.audio_duration_seconds,
            token_count=user_msg.token_count,
            created_at=user_msg.created_at
        ),
        assistant_message=MessageResponse(
            id=assistant_msg.id,
            role=assistant_msg.role,
            content=assistant_msg.content,
            message_type=assistant_msg.message_type,
            media_urls=assistant_msg.media_urls,
            audio_url=assistant_msg.audio_url,
            audio_duration_seconds=assistant_msg.audio_duration_seconds,
            token_count=assistant_msg.token_count,
            created_at=assistant_msg.created_at
        )
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
        500: {"description": "Internal server error"}
    }
)
async def delete_conversation(
    conversation_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    chat_service: ChatServiceDep = None
):
    """
    Delete a conversation and all its messages
    """
    deleted_messages = await chat_service.delete_conversation(
        conversation_id=conversation_id,
        user_id=current_user.user_id
    )

    return DeleteConversationResponse(
        success=True,
        message="Conversation deleted successfully",
        deleted_conversation_id=conversation_id,
        deleted_messages_count=deleted_messages
    )


