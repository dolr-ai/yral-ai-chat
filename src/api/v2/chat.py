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
    *,
    limit: int = Query(default=20, ge=1, le=100, description="Number of conversations to return"),
    offset: int = Query(default=0, ge=0, description="Number of conversations to skip"),
    influencer_id: str | None = Query(default=None, description="Filter by specific influencer ID"),
    current_user: CurrentUser = Depends(get_current_user),  # noqa: B008
    chat_service: ChatServiceDep,
    message_repo: MessageRepositoryDep,
    storage_service: StorageServiceDep,
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
                influencer_id=str(conv.influencer.id) if conv.influencer else "00000000-0000-0000-0000-000000000000",
                influencer=InfluencerBasicInfoV2(
                    id=str(conv.influencer.id) if conv.influencer else "00000000-0000-0000-0000-000000000000",
                    name=conv.influencer.name if conv.influencer else "unknown",
                    display_name=conv.influencer.display_name if conv.influencer else "Unknown",
                    avatar_url=conv.influencer.avatar_url if conv.influencer else None,
                    is_online=True,
                ),
                created_at=conv.created_at,
                updated_at=conv.updated_at,
                message_count=conv.message_count or 0,
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
