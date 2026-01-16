"""
Simplified unit tests for AI provider health service.
We avoid complex parametrization to keep the data flow obvious.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.ai_provider_health import AIProviderHealthService


class TestAIProviderHealthService:
    @pytest.fixture
    def mock_clients(self):
        """Standard mock clients for Gemini and OpenRouter"""
        return MagicMock(), MagicMock()

    @pytest.fixture
    def service(self, mock_clients):
        """The health service being tested"""
        return AIProviderHealthService(gemini_client=mock_clients[0], openrouter_client=mock_clients[1])

    @pytest.mark.asyncio
    async def test_check_gemini_health_is_successful(self, service, mock_clients, sample_health_result):
        """
        WHEN we check Gemini's health
        THEN it should call the Gemini client's health_check method
        """
        # Step 1: Tell the Gemini mock what to return
        gemini_mock = mock_clients[0]
        gemini_mock.health_check = AsyncMock(return_value=sample_health_result)

        # Step 2: Run the check
        result = await service.check_provider_health("Gemini")

        # Step 3: Verify output matches our sample data
        assert result.status == sample_health_result.status
        assert result.latency_ms == sample_health_result.latency_ms
        gemini_mock.health_check.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_openrouter_health_is_successful(self, service, mock_clients, sample_health_result):
        """
        WHEN we check OpenRouter's health
        THEN it should call the OpenRouter client's health_check method
        """
        # Step 1: Tell the OpenRouter mock what to return
        openrouter_mock = mock_clients[1]
        openrouter_mock.health_check = AsyncMock(return_value=sample_health_result)

        # Step 2: Run the check
        result = await service.check_provider_health("OpenRouter")

        # Step 3: Verify output matches our sample data
        assert result.status == sample_health_result.status
        assert result.latency_ms == sample_health_result.latency_ms
        openrouter_mock.health_check.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_all_providers_pings_both_clients(self, service, mock_clients, sample_health_result):
        """
        WHEN we check all providers
        THEN it should ping both Gemini and OpenRouter
        """
        gemini_mock, openrouter_mock = mock_clients

        # Setup both mocks to return 'up'
        gemini_mock.health_check = AsyncMock(return_value=sample_health_result)
        openrouter_mock.health_check = AsyncMock(return_value=sample_health_result)

        # Run multi-check
        results = await service.check_all_providers()

        # Verify both are in the results dictionary
        assert "gemini" in results
        assert "openrouter" in results
        assert results["gemini"].status == "up"
        assert results["openrouter"].status == "up"

    def test_status_summary_contains_provider_names(self, service):
        """
        VERIFY that the summary string mentions both providers
        """
        summary = service.get_provider_status_summary()
        assert "Gemini" in summary
        assert "OpenRouter" in summary
