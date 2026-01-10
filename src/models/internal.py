"""
Internal Pydantic models for service layer
"""
from pydantic import BaseModel, ConfigDict, Field


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
    table_count: int | None = Field(None, description="Total number of tables in the database")
    error: str | None = Field(None, description="Error message if status is down")


class GeminiHealth(BaseModel):
    """Gemini API health check result"""
    model_config = ConfigDict(from_attributes=True)

    status: str = Field(..., description="Service status: up or down")
    latency_ms: int | None = Field(None, description="API call latency in milliseconds")
    error: str | None = Field(None, description="Error message if status is down")


class StorageHealth(BaseModel):
    """Storage (S3) health check result"""
    model_config = ConfigDict(from_attributes=True)

    status: str = Field(..., description="Service status: up or down")
    latency_ms: int | None = Field(None, description="API call latency in milliseconds")
    error: str | None = Field(None, description="Error message if status is down")


class ServiceHealth(BaseModel):
    """General service health check result"""
    model_config = ConfigDict(from_attributes=True)

    status: str = Field(..., description="Service status: up, down, or unconfigured")
    latency_ms: int | None = Field(None, description="Latency in milliseconds")
    error: str | None = Field(None, description="Error message")
    details: dict | None = Field(None, description="Additional health details")


class ConfigHealth(BaseModel):
    """Application configuration validation result"""
    model_config = ConfigDict(from_attributes=True)

    status: str = Field(..., description="Configuration status: valid or invalid")
    errors: list[str] = Field(default_factory=list, description="List of configuration errors")
    details: dict = Field(..., description="Configuration details (sanitized)")


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

