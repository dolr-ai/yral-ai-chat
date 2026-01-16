"""
Internal Pydantic models for service layer
"""

from pydantic import BaseModel, ConfigDict, Field

from src.models.entities import MessageType


class CircuitBreakerState(BaseModel):
    """Circuit breaker state information"""

    model_config = ConfigDict(from_attributes=True)

    state: str = Field(..., description="Circuit breaker state: closed, open, or half_open")
    failure_count: int = Field(..., description="Number of consecutive failures")
    last_failure_time: float | None = Field(None, description="Timestamp of last failure")


class DatabaseHealth(BaseModel):
    """Database health check result"""

    model_config = ConfigDict(from_attributes=True)

    status: str = Field(..., description="Database status: up or down")
    latency_ms: int | None = Field(None, description="Query latency in milliseconds")
    database: str = Field(..., description="Database type")
    path: str = Field(..., description="Database file path")
    size_mb: float = Field(..., description="Database size in MB")
    pool_size: int = Field(..., description="Connection pool size")
    error: str | None = Field(None, description="Error message if status is down")


class AIProviderHealth(BaseModel):
    """AI Provider API health check result"""

    model_config = ConfigDict(from_attributes=True)

    status: str = Field(..., description="Service status: up or down")
    latency_ms: int | None = Field(None, description="API call latency in milliseconds")
    error: str | None = Field(None, description="Error message if status is down")


class CacheStats(BaseModel):
    """Cache statistics"""

    model_config = ConfigDict(from_attributes=True)

    total_items: int = Field(..., description="Total number of cached items")
    active_items: int = Field(..., description="Number of non-expired items")
    expired_items: int = Field(..., description="Number of expired items")
    max_size: int = Field(..., description="Maximum cache size")
    hits: int = Field(..., description="Number of cache hits")
    misses: int = Field(..., description="Number of cache misses")
    hit_rate: float = Field(..., description="Cache hit rate (0.0 to 1.0)")
    evictions: int = Field(..., description="Number of items evicted")


class JWTPayload(BaseModel):
    """JWT token payload"""

    model_config = ConfigDict(from_attributes=True, extra="allow")

    sub: str = Field(..., description="Subject (user ID)")
    iss: str = Field(..., description="Issuer")
    exp: int = Field(..., description="Expiration timestamp")
    iat: int | None = Field(None, description="Issued at timestamp")
    aud: str | None = Field(None, description="Audience")
    jti: str | None = Field(None, description="JWT ID")


class CharacterValidation(BaseModel):
    """Internal model for AI character validation response from LLM"""

    is_valid: bool = Field(..., description="Whether the character concept is valid and non-NSFW")
    reason: str | None = Field(None, description="Reason for invalidation (if is_valid is false)")
    name: str | None = Field(None, description="URL-friendly username (slug)")
    display_name: str | None = Field(None, description="Human-readable display name")
    bio: str | None = Field(None, description="Character biography")
    initial_greeting: str | None = Field(None, description="Initial greeting message")
    suggested_messages: list[str] | None = Field(None, description="List of suggested starter messages")
    personality_traits: dict[str, str] | None = Field(None, description="Map of personality traits")
    category: str | None = Field(None, description="Expertise or character category")
    image_prompt: str | None = Field(None, description="Detailed prompt for avatar generation")


class LLMGenerateParams(BaseModel):
    """Parameters for AI response generation"""

    user_message: str
    system_instructions: str
    conversation_history: list[object] | None = None  # Using object to avoid circular import with Message
    media_urls: list[str] | None = None
    max_tokens: int | None = None
    response_mime_type: str | None = None
    response_schema: dict[str, object] | None = None


class AIResponse(BaseModel):
    """Standard AI response structure"""

    text: str
    token_count: int


class SendMessageParams(BaseModel):
    """Parameters for ChatService.send_message"""

    conversation_id: str
    user_id: str
    content: str
    message_type: MessageType = MessageType.TEXT
    media_urls: list[str] | None = None
    audio_url: str | None = None
    audio_duration_seconds: int | None = None
    background_tasks: object | None = None
