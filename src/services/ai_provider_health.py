"""
AI Provider Health & Monitoring Service
Handles health checks for both Gemini and OpenRouter providers
"""
from loguru import logger

from src.models.internal import GeminiHealth
from src.services.gemini_client import GeminiClient
from src.services.openrouter_client import OpenRouterClient


class AIProviderHealthService:
    """Service for monitoring AI provider health"""

    def __init__(
        self,
        gemini_client: GeminiClient,
        openrouter_client: OpenRouterClient | None = None
    ):
        self.gemini_client = gemini_client
        self.openrouter_client = openrouter_client

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
        if not self.openrouter_client:
            logger.warning("OpenRouter client not configured, skipping health check")
            return GeminiHealth(
                status="unconfigured",
                error="OpenRouter client not configured",
                latency_ms=None
            )
        
        logger.info("Checking OpenRouter API health...")
        health = await self.openrouter_client.health_check()
        
        if health.status == "up":
            logger.info(f"✓ OpenRouter API is healthy (latency: {health.latency_ms}ms)")
        else:
            logger.error(f"✗ OpenRouter API is down: {health.error}")
        
        return health

    async def check_all_providers(self) -> dict[str, GeminiHealth]:
        """Check health of all configured providers"""
        logger.info("Performing comprehensive AI provider health check...")
        
        health_results = {
            "gemini": await self.check_gemini_health(),
            "openrouter": await self.check_openrouter_health(),
        }
        
        # Log summary
        all_healthy = all(h.status == "up" for h in health_results.values() if h.status != "unconfigured")
        if all_healthy:
            logger.info("✓ All AI providers are healthy")
        else:
            logger.warning("⚠ Some AI providers are experiencing issues")
        
        return health_results

    def get_provider_status_summary(self) -> str:
        """Get a human-readable summary of provider status"""
        summary = "AI Provider Status:\n"
        summary += f"  - Gemini: {'enabled' if self.gemini_client else 'disabled'}\n"
        summary += f"  - OpenRouter: {'enabled' if self.openrouter_client else 'disabled'}\n"
        return summary
