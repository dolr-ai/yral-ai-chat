"""
Response models for API endpoints
"""
from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field
from uuid import UUID
from src.models.entities import MessageType, MessageRole


class InfluencerBasicInfo(BaseModel):
    """Basic influencer information"""
    id: UUID
    name: str
    display_name: str
    avatar_url: str | None = None


class MessageResponse(BaseModel):
    """Message response model"""
    id: UUID
    role: MessageRole
    content: str | None = None
    message_type: MessageType
    media_urls: list[str] = Field(default_factory=list)
    audio_url: str | None = None
    audio_duration_seconds: int | None = None
    token_count: int | None = None
    created_at: datetime


class LastMessageInfo(BaseModel):
    """Last message information for conversation list"""
    content: str | None = None
    role: MessageRole
    created_at: datetime


class ConversationResponse(BaseModel):
    """Conversation response model"""
    id: UUID
    user_id: str
    influencer: InfluencerBasicInfo
    created_at: datetime
    updated_at: datetime
    message_count: int = 0
    last_message: LastMessageInfo | None = None


class SendMessageResponse(BaseModel):
    """Response when sending a message"""
    user_message: MessageResponse
    assistant_message: MessageResponse


class ListConversationsResponse(BaseModel):
    """Response for listing conversations"""
    conversations: list[ConversationResponse]
    total: int
    limit: int
    offset: int


class ListMessagesResponse(BaseModel):
    """Response for listing messages"""
    conversation_id: UUID
    messages: list[MessageResponse]
    total: int
    limit: int
    offset: int


class InfluencerResponse(BaseModel):
    """AI Influencer response model"""
    id: UUID
    name: str
    display_name: str
    avatar_url: str | None = None
    description: str | None = None
    category: str | None = None
    is_active: bool
    created_at: datetime
    conversation_count: int | None = None

class ListInfluencersResponse(BaseModel):
    """Response for listing influencers"""
    influencers: list[InfluencerResponse]
    total: int
    limit: int
    offset: int


class ServiceHealth(BaseModel):
    """Health status of a service"""
    status: str
    latency_ms: int | None = None
    error: str | None = None
    pool_size: int | None = None
    pool_free: int | None = None


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    timestamp: datetime
    services: dict[str, ServiceHealth]


class DatabaseStats(BaseModel):
    """Database statistics"""
    connected: bool
    pool_size: int | None = None
    active_connections: int | None = None


class SystemStatistics(BaseModel):
    """System-wide statistics"""
    total_conversations: int = 0
    total_messages: int = 0
    active_influencers: int = 0


class StatusResponse(BaseModel):
    """System status response"""
    service: str
    version: str
    environment: str
    uptime_seconds: int
    database: DatabaseStats
    statistics: SystemStatistics
    timestamp: datetime


class MediaUploadResponse(BaseModel):
    """Media upload response"""
    url: str
    type: str  # "image" or "audio"
    size: int
    mime_type: str
    duration_seconds: int | None = None
    uploaded_at: datetime


class DeleteConversationResponse(BaseModel):
    """Delete conversation response"""
    success: bool
    message: str
    deleted_conversation_id: UUID
    deleted_messages_count: int


class ErrorResponse(BaseModel):
    """Error response model"""
    error: str
    message: str
    details: dict[str, Any] | None = None


