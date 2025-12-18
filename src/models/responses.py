"""
Response models for API endpoints
"""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.models.entities import MessageRole, MessageType


class InfluencerBasicInfo(BaseModel):
    """Basic influencer information"""
    model_config = ConfigDict(
        from_attributes=True,
        use_enum_values=True,
        populate_by_name=True
    )

    id: str = Field(..., description="Unique identifier for the influencer (UUID or IC Principal)", examples=["550e8400-e29b-41d4-a716-446655440000"])
    name: str = Field(..., description="URL-friendly username", examples=["tech_guru_ai"])
    display_name: str = Field(..., description="Display name for the influencer", examples=["Tech Guru AI"])
    avatar_url: str | None = Field(None, description="Profile picture URL", examples=["https://cdn.yral.com/avatars/tech_guru.png"])
    suggested_messages: list[str] | None = Field(
        default=None,
        description="Initial suggested messages users can ask to get started",
        examples=[["Help me create a simple fitness routine", "Give me a full body workout without gym equipment"]],
    )


class MessageResponse(BaseModel):
    """Message response model"""
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    id: str = Field(..., description="Unique message identifier")
    role: MessageRole = Field(..., description="Message sender: 'user' or 'assistant'", examples=["user"])
    content: str | None = Field(None, description="Message text content", examples=["Hello! How are you today?"])
    message_type: MessageType = Field(..., description="Message type: TEXT, IMAGE, MULTIMODAL, or AUDIO", examples=["TEXT"])
    media_urls: list[str] = Field(default_factory=list, description="Array of image URLs", examples=[[]])
    audio_url: str | None = Field(None, description="URL to audio file", examples=[None])
    audio_duration_seconds: int | None = Field(None, description="Audio duration in seconds", examples=[None])
    token_count: int | None = Field(None, description="AI tokens used (assistant messages only)", examples=[150])
    created_at: datetime = Field(..., description="Message timestamp")


class LastMessageInfo(BaseModel):
    """Last message information for conversation list"""
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    content: str | None = None
    role: MessageRole
    created_at: datetime


class ConversationResponse(BaseModel):
    """Conversation response model"""
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    id: str
    user_id: str
    influencer: InfluencerBasicInfo
    created_at: datetime
    updated_at: datetime
    message_count: int = 0
    last_message: LastMessageInfo | None = None
    greeting_message: LastMessageInfo | None = None
    recent_messages: list[MessageResponse] | None = None


class SendMessageResponse(BaseModel):
    """Response when sending a message"""
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    user_message: MessageResponse
    assistant_message: MessageResponse


class ListConversationsResponse(BaseModel):
    """Response for listing conversations"""
    model_config = ConfigDict(from_attributes=True)

    conversations: list[ConversationResponse]
    total: int
    limit: int
    offset: int


class ListMessagesResponse(BaseModel):
    """Response for listing messages"""
    model_config = ConfigDict(from_attributes=True)

    conversation_id: str
    messages: list[MessageResponse]
    total: int
    limit: int
    offset: int


class InfluencerResponse(BaseModel):
    """AI Influencer response model"""
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    id: str = Field(..., description="Unique identifier for the influencer (UUID or IC Principal)")
    name: str = Field(..., description="URL-friendly username", examples=["tech_guru_ai"])
    display_name: str = Field(..., description="Display name", examples=["Tech Guru AI"])
    avatar_url: str | None = Field(None, description="Profile picture URL")
    description: str | None = Field(None, description="Bio/description of the influencer")
    category: str | None = Field(None, description="Category/expertise area", examples=["Technology"])
    is_active: bool = Field(..., description="Whether influencer is currently active")
    created_at: datetime = Field(..., description="Creation timestamp")


class ListInfluencersResponse(BaseModel):
    """Response for listing influencers"""
    model_config = ConfigDict(from_attributes=True)

    influencers: list[InfluencerResponse]
    total: int
    limit: int
    offset: int


class ServiceHealth(BaseModel):
    """Health status of a service"""
    model_config = ConfigDict(from_attributes=True)

    status: str
    latency_ms: int | None = None
    error: str | None = None
    pool_size: int | None = None
    pool_free: int | None = None


class HealthResponse(BaseModel):
    """Health check response"""
    model_config = ConfigDict(from_attributes=True)

    status: str
    timestamp: datetime
    services: dict[str, ServiceHealth]


class DatabaseStats(BaseModel):
    """Database statistics"""
    model_config = ConfigDict(from_attributes=True)

    connected: bool
    pool_size: int | None = None
    active_connections: int | None = None


class SystemStatistics(BaseModel):
    """System-wide statistics"""
    model_config = ConfigDict(from_attributes=True)

    total_conversations: int = 0
    total_messages: int = 0
    active_influencers: int = 0


class StatusResponse(BaseModel):
    """System status response"""
    model_config = ConfigDict(from_attributes=True)

    service: str
    version: str
    environment: str
    uptime_seconds: int
    database: DatabaseStats
    statistics: SystemStatistics
    timestamp: datetime


class MediaUploadResponse(BaseModel):
    """Media upload response"""
    model_config = ConfigDict(from_attributes=True)

    url: str = Field(
        ...,
        description="Temporary presigned URL of uploaded file",
        examples=["https://storage.example.com/uploads/image123.jpg?X-Amz-Expires=900&X-Amz-Signature=..."],
    )
    storage_key: str = Field(
        ...,
        description="Opaque storage key for the uploaded file, to be stored and later referenced in chat messages",
        examples=["user123/550e8400-e29b-41d4-a716-446655440000.jpg"],
    )
    type: str = Field(..., description="Media type: 'image' or 'audio'", examples=["image"])
    size: int = Field(..., description="File size in bytes", examples=[1024000])
    mime_type: str = Field(..., description="MIME type of the file", examples=["image/jpeg"])
    duration_seconds: int | None = Field(None, description="Audio duration in seconds (audio only)", examples=[None])
    uploaded_at: datetime = Field(..., description="Upload timestamp")


class DeleteConversationResponse(BaseModel):
    """Delete conversation response"""
    model_config = ConfigDict(from_attributes=True)

    success: bool
    message: str
    deleted_conversation_id: str
    deleted_messages_count: int


class ErrorResponse(BaseModel):
    """Error response model"""
    model_config = ConfigDict(from_attributes=True)

    error: str
    message: str
    details: dict[str, Any] | None = None


