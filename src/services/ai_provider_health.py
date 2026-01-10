"""
AI Provider Health & Monitoring Service
Handles health checks for both Gemini and OpenRouter providers
"""
import time

import httpx
from loguru import logger

from src.config import settings
from src.db.base import Database
from src.models.internal import (
    ConfigHealth,
    DatabaseHealth,
    GeminiHealth,
    ServiceHealth,
    StorageHealth,
)
from src.services.gemini_client import GeminiClient
from src.services.openrouter_client import OpenRouterClient
from src.services.storage_service import StorageService


class AIProviderHealthService:
    """Service for monitoring AI provider and infrastructure health"""

    def __init__(
        self,
        gemini_client: GeminiClient,
        storage_service: StorageService,
        database: Database,
        openrouter_client: OpenRouterClient | None = None
    ):
        self.gemini_client = gemini_client
        self.storage_service = storage_service
        self.database = database
        self.openrouter_client = openrouter_client

    async def check_app_config(self) -> ConfigHealth:
        """Validate application configuration"""
        logger.info("Validating application configuration...")
        errors = []
        
        # Check JWT Secret strength
        if len(settings.jwt_secret_key) < 32:
            errors.append("JWT_SECRET_KEY is too short (should be at least 32 characters)")
        if "your-super-secret" in settings.jwt_secret_key:
            errors.append("JWT_SECRET_KEY is using default placeholder value")

        # Check CORS
        cors_info = "All origins allowed (*)" if settings.cors_origins == "*" else f"Allowed: {settings.cors_origins}"

        details = {
            "app_name": settings.app_name,
            "environment": settings.environment,
            "debug": settings.debug,
            "port": settings.port,
            "jwt_algorithm": settings.jwt_algorithm,
            "cors_config": cors_info
        }

        return ConfigHealth(
            status="valid" if not errors else "invalid",
            errors=errors,
            details=details
        )

    async def check_gemini_health(self) -> GeminiHealth:
        """Check Gemini API health"""
        logger.info("Checking Gemini API health...")
        health = await self.gemini_client.health_check()
        
        if health.status == "up":
            logger.info(f"✓ Gemini API is healthy (latency: {health.latency_ms}ms)")
        else:
            logger.error(f"✗ Gemini API is down: {health.error}")
        
        return health

    async def check_openrouter_health(self) -> GeminiHealth:
        """Check OpenRouter API health"""
        if not self.openrouter_client or not settings.openrouter_api_key:
            logger.warning("OpenRouter client not configured, skipping health check")
            return GeminiHealth(
                status="unconfigured",
                error="OpenRouter API key not set",
                latency_ms=None
            )
        
        logger.info("Checking OpenRouter API health...")
        health = await self.openrouter_client.health_check()
        
        if health.status == "up":
            logger.info(f"✓ OpenRouter API is healthy (latency: {health.latency_ms}ms)")
        else:
            logger.error(f"✗ OpenRouter API is down: {health.error}")
        
        return health

    async def check_storage_health(self) -> StorageHealth:
        """Check Storage health"""
        logger.info("Checking Storage health...")
        result = await self.storage_service.health_check()
        health = StorageHealth(**result)

        if health.status == "up":
            logger.info(f"✓ Storage is healthy (latency: {health.latency_ms}ms)")
        else:
            logger.error(f"✗ Storage is down: {health.error}")

        return health

    async def check_database_health(self) -> DatabaseHealth:
        """Check Database health"""
        logger.info("Checking Database health...")
        health = await self.database.health_check()
        
        # Get table count if up
        table_count = None
        if health.status == "up":
            try:
                tables = await self.database.fetch(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
                table_count = len(tables)
                health.table_count = table_count
            except Exception as e:
                logger.warning(f"Could not fetch table count: {e}")

        if health.status == "up":
            logger.info(f"✓ Database is healthy (latency: {health.latency_ms}ms, tables: {table_count})")
        else:
            logger.error(f"✗ Database is down: {health.error}")

        return health

    async def check_litestream_health(self) -> ServiceHealth:
        """Check Litestream backup configuration"""
        if not settings.litestream_access_key_id:
            return ServiceHealth(status="unconfigured", error="Litestream not configured")
        
        details = {
            "bucket": settings.litestream_bucket,
            "endpoint": settings.litestream_endpoint,
            "region": settings.litestream_region
        }
        
        # We can't easily check if litestream process is running, 
        # but we can check if credentials are provided.
        # As a better check, we can try to list the bucket if it's S3-compatible.
        return ServiceHealth(status="configured", details=details)

    async def check_sentry_health(self) -> ServiceHealth:
        """Check Sentry configuration"""
        if not settings.sentry_dsn:
            return ServiceHealth(status="unconfigured", error="SENTRY_DSN not set")
        
        return ServiceHealth(
            status="enabled", 
            details={
                "traces_sample_rate": settings.sentry_traces_sample_rate,
                "environment": settings.sentry_environment
            }
        )

    async def check_all_providers(self) -> dict:
        """Check health of all configured services and providers"""
        logger.info("Performing comprehensive infrastructure health check...")
        
        return {
            "config": await self.check_app_config(),
            "gemini": await self.check_gemini_health(),
            "openrouter": await self.check_openrouter_health(),
            "storage": await self.check_storage_health(),
            "database": await self.check_database_health(),
            "litestream": await self.check_litestream_health(),
            "sentry": await self.check_sentry_health(),
        }

    def get_provider_status_summary(self) -> str:
        """Get a human-readable summary of provider status"""
        summary = "Service Status:\n"
        summary += f"  - Gemini: {'enabled' if self.gemini_client else 'disabled'}\n"
        summary += f"  - OpenRouter: {'enabled' if self.openrouter_client else 'disabled'}\n"
        summary += f"  - Storage: {'enabled' if self.storage_service else 'disabled'}\n"
        summary += f"  - Database: {'enabled' if self.database else 'disabled'}\n"
        return summary
