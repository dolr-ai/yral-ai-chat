"""
Configuration management for Yral AI Chat API
"""
from typing import List
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # Application
    app_name: str = Field(default="Yral AI Chat API", alias="APP_NAME")
    app_version: str = Field(default="1.0.0", alias="APP_VERSION")
    environment: str = Field(default="development", alias="ENVIRONMENT")
    debug: bool = Field(default=False, alias="DEBUG")
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT")
    
    # Database
    database_url: str = Field(..., alias="DATABASE_URL")
    db_pool_min_size: int = Field(default=5, alias="DB_POOL_MIN_SIZE")
    db_pool_max_size: int = Field(default=20, alias="DB_POOL_MAX_SIZE")
    db_pool_timeout: int = Field(default=30, alias="DB_POOL_TIMEOUT")
    
    # JWT Authentication
    jwt_secret_key: str = Field(..., alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_issuer: str = Field(default="yral_auth", alias="JWT_ISSUER")
    
    # Google Gemini API
    gemini_api_key: str = Field(..., alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.5-flash", alias="GEMINI_MODEL")
    gemini_max_tokens: int = Field(default=2048, alias="GEMINI_MAX_TOKENS")
    gemini_temperature: float = Field(default=0.7, alias="GEMINI_TEMPERATURE")
    
    # Media Storage
    media_upload_dir: str = Field(default="/root/yral-ai-chat/uploads", alias="MEDIA_UPLOAD_DIR")
    media_base_url: str = Field(default="http://localhost:8000/media", alias="MEDIA_BASE_URL")
    max_image_size_mb: int = Field(default=10, alias="MAX_IMAGE_SIZE_MB")
    max_audio_size_mb: int = Field(default=20, alias="MAX_AUDIO_SIZE_MB")
    max_audio_duration_seconds: int = Field(default=300, alias="MAX_AUDIO_DURATION_SECONDS")
    
    # Optional: AWS S3
    use_s3: bool = Field(default=False, alias="USE_S3")
    aws_access_key_id: str = Field(default="", alias="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: str = Field(default="", alias="AWS_SECRET_ACCESS_KEY")
    aws_s3_bucket: str = Field(default="", alias="AWS_S3_BUCKET")
    aws_region: str = Field(default="us-east-1", alias="AWS_REGION")
    
    # Optional: Whisper API
    use_whisper: bool = Field(default=False, alias="USE_WHISPER")
    whisper_api_key: str = Field(default="", alias="WHISPER_API_KEY")
    
    # CORS
    cors_origins: str = Field(default="*", alias="CORS_ORIGINS")
    cors_allow_credentials: bool = Field(default=True, alias="CORS_ALLOW_CREDENTIALS")
    
    # Rate Limiting
    rate_limit_per_minute: int = Field(default=60, alias="RATE_LIMIT_PER_MINUTE")
    rate_limit_per_hour: int = Field(default=1000, alias="RATE_LIMIT_PER_HOUR")
    
    # Logging
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_format: str = Field(default="json", alias="LOG_FORMAT")
    
    @property
    def cors_origins_list(self) -> List[str]:
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
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings()


