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
    # Entities
    "AIInfluencer",
    "Conversation",
    # Responses
    "ConversationResponse",
    # Requests
    "CreateConversationRequest",
    "DeleteConversationResponse",
    "HealthResponse",
    "InfluencerResponse",
    "ListConversationsResponse",
    "ListInfluencersResponse",
    "ListMessagesResponse",
    "MediaUploadResponse",
    "Message",
    "MessageResponse",
    # Enums
    "MessageRole",
    "MessageType",
    "SendMessageRequest",
    "SendMessageResponse",
    "StatusResponse",
]


