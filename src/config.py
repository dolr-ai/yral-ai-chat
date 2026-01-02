"""
Configuration management for Yral AI Chat API
"""
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Application
    app_name: str = Field(default="Yral AI Chat API", alias="APP_NAME")
    app_version: str = Field(default="1.0.0", alias="APP_VERSION")
    environment: Literal["development", "staging", "production"] = Field(
        default="development",
        alias="ENVIRONMENT"
    )
    debug: bool = Field(default=False, alias="DEBUG")
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, ge=1, le=65535, alias="PORT")

    # Database (SQLite with Litestream)
    database_path: str = Field(default="/root/yral-ai-chat/data/yral_chat.db", alias="DATABASE_PATH")
    database_pool_size: int = Field(default=5, ge=1, le=20, alias="DATABASE_POOL_SIZE")
    database_pool_timeout: float = Field(default=30.0, gt=0, alias="DATABASE_POOL_TIMEOUT")

    # JWT Authentication
    jwt_secret_key: str = Field(..., alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_issuer: str = Field(default="yral_auth", alias="JWT_ISSUER")

    # Google Gemini API
    gemini_api_key: str = Field(..., min_length=1, alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.5-flash", alias="GEMINI_MODEL")
    gemini_max_tokens: int = Field(default=2048, ge=1, le=8192, alias="GEMINI_MAX_TOKENS")
    gemini_temperature: float = Field(default=0.7, ge=0.0, le=2.0, alias="GEMINI_TEMPERATURE")

    # Media Storage
    max_image_size_mb: int = Field(default=10, ge=1, le=100, alias="MAX_IMAGE_SIZE_MB")
    max_audio_size_mb: int = Field(default=20, ge=1, le=200, alias="MAX_AUDIO_SIZE_MB")
    max_audio_duration_seconds: int = Field(default=300, ge=1, le=600, alias="MAX_AUDIO_DURATION_SECONDS")

    # S3 Storage (Required)
    aws_access_key_id: str = Field(..., min_length=1, alias="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: str = Field(..., min_length=1, alias="AWS_SECRET_ACCESS_KEY")
    aws_s3_bucket: str = Field(..., min_length=1, alias="AWS_S3_BUCKET")
    aws_region: str = Field(..., min_length=1, alias="AWS_REGION")
    s3_endpoint_url: str = Field(..., alias="S3_ENDPOINT_URL")
    s3_public_url_base: str = Field(..., alias="S3_PUBLIC_URL_BASE")
    s3_url_expires_seconds: int = Field(
        default=900,
        ge=60,
        le=86400,
        alias="S3_URL_EXPIRES_SECONDS",
        description="Expiration time in seconds for generated S3 presigned URLs",
    )

    @field_validator("s3_endpoint_url", "s3_public_url_base")
    @classmethod
    def validate_urls(cls, v: str) -> str:
        """Validate URL format"""
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v.rstrip("/")

    # Optional: Whisper API
    use_whisper: bool = Field(default=False, alias="USE_WHISPER")
    whisper_api_key: str = Field(default="", alias="WHISPER_API_KEY")

    # CORS
    cors_origins: str = Field(default="*", alias="CORS_ORIGINS")
    cors_allow_credentials: bool = Field(default=True, alias="CORS_ALLOW_CREDENTIALS")

    # Rate Limiting
    # Conservative defaults to prevent resource exhaustion:
    # - Database pool: 5-20 connections (default 5)
    # - SQLite concurrency limitations
    # - Gemini API costs and rate limits
    # - Memory usage for token buckets
    # Max safe values can be set via environment variables if needed
    rate_limit_per_minute: int = Field(default=300, ge=1, le=10000, alias="RATE_LIMIT_PER_MINUTE")
    rate_limit_per_hour: int = Field(default=5000, ge=1, le=100000, alias="RATE_LIMIT_PER_HOUR")

    @field_validator("rate_limit_per_hour")
    @classmethod
    def validate_rate_limits(cls, v: int, info) -> int:
        """Ensure hourly limit is greater than per-minute limit"""
        if "rate_limit_per_minute" in info.data:
            per_minute = info.data["rate_limit_per_minute"]
            if v < per_minute:
                raise ValueError("Hourly rate limit must be >= per-minute rate limit")
        return v

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        alias="LOG_LEVEL"
    )
    log_format: Literal["json", "text"] = Field(default="json", alias="LOG_FORMAT")

    # Sentry Error Tracking & Performance Monitoring
    sentry_dsn: str | None = Field(
        default=None,
        alias="SENTRY_DSN",
        description="Sentry DSN URL for error tracking. Format: https://<key>@apm.yral.com/<project_id>"
    )
    sentry_traces_sample_rate: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        alias="SENTRY_TRACES_SAMPLE_RATE",
        description="Performance monitoring sample rate (0.0 to 1.0). Default: 1.0 for production, recommend 0.1 for development"
    )
    sentry_profiles_sample_rate: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        alias="SENTRY_PROFILES_SAMPLE_RATE",
        description="Profiling sample rate (0.0 to 1.0). Default: 0.0 (disabled)"
    )

    @property
    def sentry_environment(self) -> str:
        """Map application environment to Sentry environment"""
        return self.environment

    @property
    def sentry_release(self) -> str:
        """Use app version as Sentry release for deployment tracking"""
        return self.app_version

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS origins into a list"""
        if self.cors_origins == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",")]

    @property
    def max_image_size_bytes(self) -> int:
        """Convert MB to bytes"""
        return self.max_image_size_mb * 1024 * 1024

    @property
    def max_audio_size_bytes(self) -> int:
        """Convert MB to bytes"""
        return self.max_audio_size_mb * 1024 * 1024

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore"  # Allow extra fields like Litestream configs that aren't used by the app
    )


# Global settings instance
settings = Settings()


