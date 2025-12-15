"""
Request models for API endpoints
"""
from pydantic import BaseModel, Field, validator, root_validator
from uuid import UUID
from src.models.entities import MessageType


class CreateConversationRequest(BaseModel):
    """Request to create a new conversation"""
    influencer_id: UUID = Field(..., description="ID of the AI influencer")


class SendMessageRequest(BaseModel):
    """Request to send a message in a conversation"""
    message_type: MessageType = Field(..., description="Type of message")
    content: str | None = Field(
        default="",
        max_length=4000,
        description="Message text content (optional for image/audio-only messages)"
    )
    media_urls: list[str] | None = Field(
        default=None,
        max_items=10,
        description="Array of image URLs (max 10)"
    )
    audio_url: str | None = Field(
        default=None,
        description="URL to audio file"
    )
    audio_duration_seconds: int | None = Field(
        default=None,
        ge=0,
        le=300,
        description="Audio duration in seconds (max 300)"
    )
    
    @validator('message_type')
    def validate_message_type(cls, v):
        """Validate message type is valid"""
        if v not in [MessageType.TEXT, MessageType.IMAGE, MessageType.MULTIMODAL, MessageType.AUDIO]:
            raise ValueError("Invalid message type")
        return v
    
    @validator('content')
    def validate_content(cls, v):
        """Validate content length"""
        if v and len(v) > 4000:
            raise ValueError("content exceeds 4000 characters")
        return v or ""
    
    @validator('media_urls', pre=True, always=True)
    def validate_media_urls(cls, v, values):
        """Validate media URLs based on message type"""
        # Ensure v is always a list or empty list
        if v is None:
            v = []
        elif not isinstance(v, list):
            v = [v] if v else []
        
        message_type = values.get('message_type')
        
        if message_type in [MessageType.IMAGE, MessageType.MULTIMODAL]:
            if not v or len(v) == 0:
                raise ValueError("media_urls required for image/multimodal type")
            if len(v) > 10:
                raise ValueError("Too many media URLs (max 10)")
        
        return v
    
    @validator('audio_url')
    def validate_audio_url(cls, v, values):
        """Validate audio URL based on message type"""
        message_type = values.get('message_type')
        
        if message_type == MessageType.AUDIO and not v:
            raise ValueError("audio_url required for audio type")
        
        return v
    
    @validator('audio_duration_seconds')
    def validate_audio_duration(cls, v, values):
        """Validate audio duration based on message type"""
        message_type = values.get('message_type')
        
        if message_type == MessageType.AUDIO and v is not None:
            if v < 0 or v > 300:
                raise ValueError("audio_duration_seconds must be between 0 and 300")
        
        return v
    
    @root_validator(skip_on_failure=True)
    def validate_message_content(cls, values):
        """Ensure message has at least some content based on message type"""
        content = values.get('content') or ''
        media_urls = values.get('media_urls') or []
        audio_url = values.get('audio_url')
        message_type = values.get('message_type')
        
        # Check content based on type
        if message_type == MessageType.TEXT:
            if not content.strip():
                raise ValueError("content is required for text messages")
        elif message_type == MessageType.IMAGE:
            if not media_urls:
                raise ValueError("media_urls is required for image messages")
        elif message_type == MessageType.MULTIMODAL:
            if not media_urls:
                raise ValueError("media_urls is required for multimodal messages")
        elif message_type == MessageType.AUDIO:
            if not audio_url:
                raise ValueError("audio_url is required for audio messages")
        
        return values


