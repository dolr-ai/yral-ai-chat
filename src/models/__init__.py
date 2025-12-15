"""Pydantic models package"""
from src.models.entities import AIInfluencer, Conversation, Message, MessageRole, MessageType
from src.models.requests import CreateConversationRequest, SendMessageRequest
from src.models.responses import (
    ConversationResponse,
    DeleteConversationResponse,
    HealthResponse,
    InfluencerResponse,
    ListConversationsResponse,
    ListInfluencersResponse,
    ListMessagesResponse,
    MediaUploadResponse,
    MessageResponse,
    SendMessageResponse,
    StatusResponse,
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


