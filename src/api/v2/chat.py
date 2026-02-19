"""
Chat endpoints (V2 - Strict Schema)
"""

from fastapi import APIRouter, Depends, Query

from src.auth.jwt_auth import CurrentUser, get_current_user
from src.core.dependencies import ChatServiceDep, MessageRepositoryDep, StorageServiceDep
from src.models.responses import (
    ConversationResponseV2,
    InfluencerBasicInfoV2,
    ListConversationsResponseV2,
)

router = APIRouter(prefix="/api/v2/chat", tags=["Chat V2"])


@router.get(
    "/conversations",
    response_model=ListConversationsResponseV2,
    operation_id="listConversationsV2",
    summary="List user conversations (V2)",
    description="Retrieve list of user's conversations with strict schema (unread_count and last_message).",
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
    List user's conversations (V2)
    
    Returns conversations with unread_count and last_message info.
    """
    conversations, _total = await chat_service.list_conversations(
        user_id=current_user.user_id,
        influencer_id=influencer_id,
        limit=limit,
        offset=offset,
    )

    conversation_responses = []
    
    for conv in conversations:
        conversation_responses.append(
            ConversationResponseV2(
                id=conv.id,
                user_id=conv.user_id,
                influencer_id=conv.influencer.id,
                influencer=InfluencerBasicInfoV2(
                    id=conv.influencer.id,
                    display_name=conv.influencer.display_name,
                    avatar_url=conv.influencer.avatar_url,
                    is_online=True,
                ),
                created_at=conv.created_at,
                updated_at=conv.updated_at,
                unread_count=conv.unread_count,
                last_message=conv.last_message,
            )
        )

    return ListConversationsResponseV2(
        conversations=conversation_responses,
        total=len(conversation_responses),
        limit=limit,
        offset=offset,
    )
