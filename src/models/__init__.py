"""Pydantic models package"""
from src.models.entities import (
    MessageType,
    MessageRole,
    AIInfluencer,
    Conversation,
    Message
)
from src.models.requests import (
    CreateConversationRequest,
    SendMessageRequest
)
from src.models.responses import (
    ConversationResponse,
    MessageResponse,
    SendMessageResponse,
    ListConversationsResponse,
    ListMessagesResponse,
    InfluencerResponse,
    ListInfluencersResponse,
    HealthResponse,
    StatusResponse,
    MediaUploadResponse,
    DeleteConversationResponse
)

__all__ = [
    # Enums
    "MessageType",
    "MessageRole",
    # Entities
    "AIInfluencer",
    "Conversation",
    "Message",
    # Requests
    "CreateConversationRequest",
    "SendMessageRequest",
    # Responses
    "ConversationResponse",
    "MessageResponse",
    "SendMessageResponse",
    "ListConversationsResponse",
    "ListMessagesResponse",
    "InfluencerResponse",
    "ListInfluencersResponse",
    "HealthResponse",
    "StatusResponse",
    "MediaUploadResponse",
    "DeleteConversationResponse",
]


