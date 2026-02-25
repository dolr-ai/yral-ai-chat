"""
AI Provider Health & Monitoring Service
Handles health checks for both Gemini and OpenRouter providers
"""

from loguru import logger
from pydantic import validate_call

from src.models.internal import AIProviderHealth
from src.services.gemini_client import GeminiClient
from src.services.openrouter_client import OpenRouterClient


class AIProviderHealthService:
    """Service for monitoring AI provider health"""

    def __init__(self, gemini_client: GeminiClient, openrouter_client: OpenRouterClient | None = None):
        self.gemini_client = gemini_client
        self.openrouter_client = openrouter_client

    @validate_call
    async def check_provider_health(self, provider_name: str) -> AIProviderHealth:
        """Check specific AI provider API health"""
        client: GeminiClient | OpenRouterClient | None = None
        if provider_name.lower() == "gemini":
            client = self.gemini_client
        elif provider_name.lower() == "openrouter":
            client = self.openrouter_client

        if not client:
            logger.warning(f"Provider {provider_name} not configured, skipping health check")
            return AIProviderHealth(
                status="unconfigured", error=f"Provider {provider_name} not configured", latency_ms=None
            )

        logger.info(f"Checking {provider_name} API health...")
        health = await client.health_check()

        if health.status == "up":
            logger.info(f"✓ {provider_name} API is healthy (latency: {health.latency_ms}ms)")
        else:
            logger.error(f"✗ {provider_name} API is down: {health.error}")

        return health

    async def check_all_providers(self) -> dict[str, AIProviderHealth]:
        """Check health of all configured providers"""
        logger.info("Performing comprehensive AI provider health check...")

        health_results = {
            "gemini": await self.check_provider_health("Gemini"),
            "openrouter": await self.check_provider_health("OpenRouter"),
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
