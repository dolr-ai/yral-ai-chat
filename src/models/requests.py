"""
Request models for API endpoints
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.models.entities import MessageType


class CreateConversationRequest(BaseModel):
    """Request to create a new conversation"""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        use_enum_values=False,
        validate_assignment=True,
        arbitrary_types_allowed=False,
        json_schema_extra={"examples": [{"influencer_id": "550e8400-e29b-41d4-a716-446655440000"}]},
    )

    influencer_id: str = Field(
        ...,
        description="ID of the AI influencer (UUID or IC Principal)",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )


class SendMessageRequest(BaseModel):
    """Request to send a message in a conversation"""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        use_enum_values=False,
        validate_assignment=True,
        arbitrary_types_allowed=False,
        json_schema_extra={
            "examples": [
                {
                    "message_type": "TEXT",
                    "content": "Hello! How are you today?",
                    "media_urls": None,
                    "audio_url": None,
                    "audio_duration_seconds": None,
                },
                {
                    "message_type": "IMAGE",
                    "content": "What's in this image?",
                    "media_urls": ["https://example.com/image.jpg"],
                    "audio_url": None,
                    "audio_duration_seconds": None,
                },
                {
                    "message_type": "AUDIO",
                    "content": "",
                    "media_urls": None,
                    "audio_url": "https://example.com/audio.mp3",
                    "audio_duration_seconds": 45,
                },
            ]
        },
    )

    message_type: MessageType = Field(
        ..., description="Type of message: TEXT, IMAGE, MULTIMODAL, or AUDIO", examples=["TEXT"]
    )
    content: str | None = Field(
        default="",
        max_length=4000,
        description="Message text content (optional for image/audio-only messages)",
        examples=["Hello! How are you today?"],
    )
    media_urls: list[str] | None = Field(
        default=None,
        max_length=10,
        description="Array of storage keys from the upload endpoint (max 10). These are the storage_key values returned by POST /api/v1/media/upload.",
        examples=[["user123/550e8400-e29b-41d4-a716-446655440000.jpg"]],
    )
    audio_url: str | None = Field(
        default=None,
        description="Storage key from the upload endpoint. This is the storage_key value returned by POST /api/v1/media/upload.",
        examples=["user123/550e8400-e29b-41d4-a716-446655440000.mp3"],
    )
    audio_duration_seconds: int | None = Field(
        default=None, ge=0, le=300, description="Audio duration in seconds (max 300)", examples=[45]
    )
    client_message_id: str | None = Field(
        default=None,
        description="Optional unique identifier for deduplication (UUID format recommended)",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )

    @field_validator("message_type", mode="before")
    @classmethod
    def normalize_message_type(cls, v: str | MessageType) -> str | MessageType:
        """Normalize message type to lowercase to accept both uppercase and lowercase"""
        if isinstance(v, str):
            return v.lower()
        return v

    @field_validator("message_type")
    @classmethod
    def validate_message_type(cls, v: MessageType) -> MessageType:
        """Validate message type is valid"""
        valid_types = {MessageType.TEXT, MessageType.IMAGE, MessageType.MULTIMODAL, MessageType.AUDIO}
        if v not in valid_types:
            raise ValueError("Invalid message type")
        return v

    @field_validator("content", mode="before")
    @classmethod
    def validate_content_before(cls, v):
        """Convert content to string if it's a number or other type"""
        if v is None:
            return None
        if not isinstance(v, str):
            return str(v)
        return v

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str | None) -> str:
        """Validate content length"""
        if v and len(v) > 4000:
            raise ValueError("content exceeds 4000 characters")
        return v or ""

    @field_validator("media_urls", mode="before")
    @classmethod
    def validate_media_urls_format(cls, v):
        """Ensure media_urls is always a list"""
        if v is None:
            return []
        if not isinstance(v, list):
            return [v] if v else []
        return v

    @model_validator(mode="after")
    def validate_message_content(self):
        """Ensure message has at least some content based on message type"""
        content = self.content or ""
        media_urls = self.media_urls or []
        audio_url = self.audio_url
        message_type = self.message_type

        self._validate_text_message(message_type, content)
        self._validate_image_message(message_type, media_urls)
        self._validate_multimodal_message(message_type, media_urls)
        self._validate_audio_message(message_type, audio_url)

        return self

    def _validate_text_message(self, message_type: MessageType, content: str) -> None:
        """Validate text message requirements"""
        if message_type == MessageType.TEXT and not content.strip():
            raise ValueError("content is required for text messages")

    def _validate_image_message(self, message_type: MessageType, media_urls: list[str]) -> None:
        """Validate image message requirements"""
        if message_type == MessageType.IMAGE:
            if not media_urls:
                raise ValueError("media_urls is required for image messages")
            if len(media_urls) > 10:
                raise ValueError("Too many media URLs (max 10)")

    def _validate_multimodal_message(self, message_type: MessageType, media_urls: list[str]) -> None:
        """Validate multimodal message requirements"""
        if message_type == MessageType.MULTIMODAL:
            if not media_urls:
                raise ValueError("media_urls is required for multimodal messages")
            if len(media_urls) > 10:
                raise ValueError("Too many media URLs (max 10)")

    def _validate_audio_message(self, message_type: MessageType, audio_url: str | None) -> None:
        """Validate audio message requirements"""
        if message_type == MessageType.AUDIO and not audio_url:
            raise ValueError("audio_url is required for audio messages")


class GeneratePromptRequest(BaseModel):
    """Request to generate system instructions from a prompt"""

    model_config = ConfigDict(str_strip_whitespace=True)

    prompt: str = Field(..., max_length=1000, description="Character concept prompt", examples=["a geeky teacher"])


class ValidateMetadataRequest(BaseModel):
    """Request to validate instructions and generate metadata"""

    model_config = ConfigDict(str_strip_whitespace=True)

    system_instructions: str = Field(..., description="System instructions to validate")


class CreateInfluencerRequest(BaseModel):
    """Request to create a new influencer"""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(
        ..., min_length=3, max_length=15, description="Internal name (slug) - 3-15 alphanumeric characters"
    )
    display_name: str = Field(..., min_length=1, max_length=100, description="Display name")
    description: str | None = Field(None, max_length=500, description="Short bio")
    system_instructions: str = Field(..., description="System prompts for the AI")
    initial_greeting: str | None = Field(None, description="First message sent by the AI")
    suggested_messages: list[str] = Field(default_factory=list, max_length=10, description="Suggested user starters")
    personality_traits: dict[str, object] = Field(default_factory=dict, description="Key-value pairs of traits")
    category: str | None = Field(None, description="Character category")
    avatar_url: str | None = Field(None, description="URL of the avatar image")
    is_nsfw: bool = Field(default=False, description="Whether the character is NSFW (Ignored: Enforced to False)")
    bot_principal_id: str = Field(..., description="ID of the bot principal (used as primary ID)")

    @field_validator("name")
    @classmethod
    def validate_name_alphanumeric(cls, v: str) -> str:
        """Validate that name is alphanumeric only (3-12 characters)"""
        if not v.isalnum():
            raise ValueError("name must contain only alphanumeric characters (letters and numbers)")
        return v


class GenerateImageRequest(BaseModel):
    """Request to generate an image in a conversation"""

    model_config = ConfigDict(str_strip_whitespace=True)

    prompt: str | None = Field(
        None,
        max_length=1000,
        description="Optional prompt for image generation. If not provided, one will be generated from conversation history.",
        examples=["A futuristic city skyline"],
    )


class UpdateSystemPromptRequest(BaseModel):
    """Request to update an influencer's system prompt"""

    model_config = ConfigDict(str_strip_whitespace=True)

    system_instructions: str = Field(..., min_length=1, description="New system instructions for the AI")
