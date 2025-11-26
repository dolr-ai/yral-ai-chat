"""
Chat endpoints
"""
from fastapi import APIRouter, Depends, Query
from fastapi.security import HTTPBearer
from uuid import UUID
from typing import Optional
from src.models.requests import CreateConversationRequest, SendMessageRequest
from src.models.responses import (
    ConversationResponse,
    SendMessageResponse,
    ListConversationsResponse,
    ListMessagesResponse,
    DeleteConversationResponse,
    MessageResponse,
    InfluencerBasicInfo,
    LastMessageInfo
)
from src.services.chat_service import chat_service
from src.auth.jwt_auth import get_current_user, CurrentUser

security = HTTPBearer()
router = APIRouter(prefix="/api/v1/chat", tags=["Chat"])


@router.post("/conversations", response_model=ConversationResponse, status_code=201)
async def create_conversation(
    request: CreateConversationRequest,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Create a new conversation with an AI influencer
    
    Returns existing conversation if one already exists
    """
    conversation = await chat_service.create_conversation(
        user_id=current_user.user_id,
        influencer_id=request.influencer_id
    )
    
    # Get message count
    from src.db.repositories import MessageRepository
    message_repo = MessageRepository()
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


@router.get("/conversations", response_model=ListConversationsResponse)
async def list_conversations(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    influencer_id: Optional[UUID] = Query(default=None),
    current_user: CurrentUser = Depends(get_current_user)
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
                content=conv.last_message.get('content'),
                role=conv.last_message.get('role'),
                created_at=conv.last_message.get('created_at')
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


@router.get("/conversations/{conversation_id}/messages", response_model=ListMessagesResponse)
async def list_messages(
    conversation_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    order: str = Query(default="desc", regex="^(asc|desc)$"),
    current_user: CurrentUser = Depends(get_current_user)
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


@router.post("/conversations/{conversation_id}/messages", response_model=SendMessageResponse)
async def send_message(
    conversation_id: UUID,
    request: SendMessageRequest,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Send a message to AI influencer
    
    Supports:
    - Text-only messages
    - Image-only messages
    - Text + Image messages (multimodal)
    - Audio/voice messages
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


@router.delete("/conversations/{conversation_id}", response_model=DeleteConversationResponse)
async def delete_conversation(
    conversation_id: UUID,
    current_user: CurrentUser = Depends(get_current_user)
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


