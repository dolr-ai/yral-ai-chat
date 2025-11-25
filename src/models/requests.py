"""
Request models for API endpoints
"""
from typing import Optional, List
from pydantic import BaseModel, Field, validator
from uuid import UUID
from src.models.entities import MessageType


class CreateConversationRequest(BaseModel):
    """Request to create a new conversation"""
    influencer_id: UUID = Field(..., description="ID of the AI influencer")


class SendMessageRequest(BaseModel):
    """Request to send a message in a conversation"""
    content: Optional[str] = Field(
        default="",
        max_length=4000,
        description="Message text content (optional for image/audio-only messages)"
    )
    message_type: MessageType = Field(..., description="Type of message")
    media_urls: Optional[List[str]] = Field(
        default=None,
        max_items=10,
        description="Array of image URLs (max 10)"
    )
    audio_url: Optional[str] = Field(
        default=None,
        description="URL to audio file"
    )
    audio_duration_seconds: Optional[int] = Field(
        default=None,
        ge=0,
        le=300,
        description="Audio duration in seconds (max 300)"
    )
    
    @validator('content')
    def validate_content(cls, v):
        """Validate content length"""
        if v and len(v) > 4000:
            raise ValueError("content exceeds 4000 characters")
        return v
    
    @validator('media_urls')
    def validate_media_urls(cls, v, values):
        """Validate media URLs based on message type"""
        message_type = values.get('message_type')
        
        if message_type in [MessageType.IMAGE, MessageType.MULTIMODAL]:
            if not v or len(v) == 0:
                raise ValueError("media_urls required for image/multimodal type")
            if len(v) > 10:
                raise ValueError("Too many media URLs (max 10)")
        
        return v or []
    
    @validator('audio_url')
    def validate_audio_url(cls, v, values):
        """Validate audio URL based on message type"""
        message_type = values.get('message_type')
        
        if message_type == MessageType.AUDIO and not v:
            raise ValueError("audio_url required for audio type")
        
        return v
    
    @validator('message_type', always=True)
    def validate_message_has_content(cls, v, values):
        """Ensure message has at least some content"""
        content = values.get('content', '')
        media_urls = values.get('media_urls', [])
        audio_url = values.get('audio_url')
        
        has_content = bool(content) or bool(media_urls) or bool(audio_url)
        
        if not has_content:
            raise ValueError("At least content, media_urls, or audio_url must be provided")
        
        return v


