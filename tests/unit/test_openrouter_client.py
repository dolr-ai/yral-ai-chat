"""
Unit tests for OpenRouter AI client, Provider health service, and NSFW routing

Tests cover:
- OpenRouter client initialization
- Health checks for both providers
- NSFW influencer filtering
- Provider selection logic
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.openrouter_client import OpenRouterClient
from src.services.ai_provider_health import AIProviderHealthService


class TestOpenRouterClientInitialization:
    """Test OpenRouter client initialization"""

    @patch("src.services.openrouter_client.settings")
    @patch("httpx.AsyncClient")
    def test_client_initialization(self, mock_http, mock_settings):
        """Test that client initializes correctly"""
        mock_settings.openrouter_api_key = "test-key-12345"
        mock_settings.openrouter_model = "google/gemini-2.5-flash:free"
        mock_settings.openrouter_max_tokens = 2000
        mock_settings.openrouter_temperature = 0.7
        mock_settings.openrouter_timeout = 30

        client = OpenRouterClient()

        assert client.api_key == "test-key-12345"
        assert client.model_name == "google/gemini-2.5-flash:free"
        assert client.max_tokens == 2000
        assert client.temperature == 0.7
        assert client.api_base == "https://openrouter.ai/api/v1"

    @patch("src.services.openrouter_client.settings")
    @patch("httpx.AsyncClient")
    def test_client_http_headers(self, mock_http, mock_settings):
        """Test client includes proper auth headers"""
        mock_settings.openrouter_api_key = "test-key-12345"
        mock_settings.openrouter_model = "google/gemini-2.5-flash:free"
        mock_settings.openrouter_max_tokens = 4000
        mock_settings.openrouter_temperature = 0.7
        mock_settings.openrouter_timeout = 30

        client = OpenRouterClient()

        call_kwargs = mock_http.call_args[1]
        assert call_kwargs["headers"]["Authorization"] == "Bearer test-key-12345"
        assert call_kwargs["headers"]["HTTP-Referer"] == "https://yral.com"


class TestAIProviderHealthService:
    """Test AI provider health checking"""

    @pytest.mark.asyncio
    @patch("src.services.ai_provider_health.GeminiClient")
    @patch("src.services.ai_provider_health.OpenRouterClient")
    async def test_check_gemini_health_success(self, mock_openrouter, mock_gemini):
        """Test successful Gemini health check"""
        from src.models.internal import GeminiHealth

        mock_gemini_instance = mock_gemini.return_value
        mock_health = GeminiHealth(status="up", latency_ms=123, error=None)
        mock_gemini_instance.health_check = AsyncMock(return_value=mock_health)

        service = AIProviderHealthService(mock_gemini_instance, mock_openrouter.return_value)
        result = await service.check_gemini_health()

        assert result.status == "up"
        mock_gemini_instance.health_check.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.services.ai_provider_health.GeminiClient")
    @patch("src.services.ai_provider_health.OpenRouterClient")
    async def test_check_openrouter_health_success(self, mock_openrouter, mock_gemini):
        """Test successful OpenRouter health check"""
        from src.models.internal import GeminiHealth

        mock_openrouter_instance = mock_openrouter.return_value
        mock_health = GeminiHealth(status="up", latency_ms=456, error=None)
        mock_openrouter_instance.health_check = AsyncMock(return_value=mock_health)

        service = AIProviderHealthService(mock_gemini.return_value, mock_openrouter_instance)
        result = await service.check_openrouter_health()

        assert result.status == "up"
        mock_openrouter_instance.health_check.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.services.ai_provider_health.GeminiClient")
    @patch("src.services.ai_provider_health.OpenRouterClient")
    async def test_check_all_providers(self, mock_openrouter, mock_gemini):
        """Test checking all providers at once"""
        from src.models.internal import GeminiHealth

        mock_gemini_instance = mock_gemini.return_value
        mock_gemini_health = GeminiHealth(status="up", latency_ms=123, error=None)
        mock_gemini_instance.health_check = AsyncMock(return_value=mock_gemini_health)

        mock_openrouter_instance = mock_openrouter.return_value
        mock_openrouter_health = GeminiHealth(status="up", latency_ms=456, error=None)
        mock_openrouter_instance.health_check = AsyncMock(return_value=mock_openrouter_health)

        service = AIProviderHealthService(mock_gemini_instance, mock_openrouter_instance)
        results = await service.check_all_providers()

        assert results["gemini"].status == "up"
        assert results["openrouter"].status == "up"

    def test_get_provider_status_summary(self):
        """Test provider status summary generation"""
        mock_gemini_instance = MagicMock()
        mock_openrouter_instance = MagicMock()

        service = AIProviderHealthService(mock_gemini_instance, mock_openrouter_instance)
        summary = service.get_provider_status_summary()

        assert "Gemini" in summary
        assert "OpenRouter" in summary
        assert "enabled" in summary
