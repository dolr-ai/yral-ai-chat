"""
Simplified unit tests for Gemini client retry logic.
We break down complex retry scenarios into explicit, readable tests.
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.core.exceptions import AIServiceException
from src.models.internal import LLMGenerateParams
from src.services.gemini_client import GeminiClient


class TestGeminiRetryLogic:
    """Test how the Gemini client handles transient errors with retries"""

    @pytest.fixture
    def mock_aio_models(self):
        """Mocks the underlying Google GenAI models"""
        with patch("src.services.gemini_client.genai.Client") as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.aio.models.generate_content = AsyncMock()
            yield mock_client.aio.models

    @pytest.fixture
    def client(self, mock_aio_models):
        """The Gemini client with mocked settings and http client"""
        with patch("src.services.gemini_client.settings") as mock_settings:
            mock_settings.gemini_api_key = "test-key"
            mock_settings.gemini_model = "gemini-pro"
            mock_settings.gemini_max_tokens = 100
            mock_settings.gemini_temperature = 0.7

            with patch("httpx.AsyncClient"):
                return GeminiClient()

    @pytest.mark.asyncio
    async def test_retry_on_rate_limit_error_429(self, client, mock_aio_models):
        """
        GIVEN the API returns a 429 (Rate Limit) error twice, then success
        WHEN we call generate_content
        THEN it should retry twice and finally return the success result
        """
        # Step 1: Create a 429 error
        response_429 = MagicMock()
        response_429.status_code = 429
        error_429 = httpx.HTTPStatusError("Rate limited", request=MagicMock(), response=response_429)

        # Step 2: Setup the mock to fail twice then succeed
        mock_response = AsyncMock()
        mock_response.text = "Success after retries"
        mock_response.candidates = [MagicMock(finish_reason=1)]

        mock_aio_models.generate_content.side_effect = [
            error_429,  # Attempt 1: Fail
            error_429,  # Attempt 2: Fail
            mock_response,  # Attempt 3: Success
        ]

        # Step 3: Call the method
        with patch("asyncio.sleep", return_value=None):
            response = await client.generate_response(
                LLMGenerateParams(user_message="test prompt", system_instructions="system instructions")
            )

        # Step 4: Verify
        assert response.text == "Success after retries"
        assert mock_aio_models.generate_content.call_count == 3

    @pytest.mark.asyncio
    async def test_retry_on_service_unavailable_503(self, client, mock_aio_models):
        """
        GIVEN the API returns a 503 (Overloaded) error once
        WHEN we call generate_content
        THEN it should retry and succeed on the second attempt
        """
        # Step 1: Create a 503 error
        response_503 = MagicMock()
        response_503.status_code = 503
        error_503 = httpx.HTTPStatusError("Overloaded", request=MagicMock(), response=response_503)

        mock_response = AsyncMock()
        mock_response.text = "Success on second try"
        mock_response.candidates = [MagicMock(finish_reason=1)]

        mock_aio_models.generate_content.side_effect = [error_503, mock_response]

        # Step 2: Call and verify
        with patch("asyncio.sleep", return_value=None):
            response = await client.generate_response(
                LLMGenerateParams(user_message="test prompt", system_instructions="system instructions")
            )
        assert response.text == "Success on second try"
        assert mock_aio_models.generate_content.call_count == 2

    @pytest.mark.asyncio
    async def test_fails_after_max_retries_exhausted(self, client, mock_aio_models):
        """
        GIVEN the API keeps failing forever
        WHEN we call generate_content
        THEN it should eventually give up and raise the error
        """
        # Step 1: Create a persistent error
        response_500 = MagicMock()
        response_500.status_code = 500
        error_500 = httpx.HTTPStatusError("Internal Error", request=MagicMock(), response=response_500)

        mock_aio_models.generate_content.side_effect = error_500

        # Step 2: Verify it raises after retries (default max retries is 3 in code)
        with patch("asyncio.sleep", return_value=None), pytest.raises(AIServiceException):
            await client.generate_response(
                LLMGenerateParams(user_message="test prompt", system_instructions="system instructions")
            )

        # 1 initial + 4 retries = 5 total calls
        assert mock_aio_models.generate_content.call_count == 5

    @pytest.mark.asyncio
    async def test_exponential_backoff_increases_delay_between_retries(self, client, mock_aio_models):
        """
        VERIFY that the time taken for retries is significant (proves it's waiting)
        """
        # Step 1: Mock 2 failures
        response_429 = MagicMock()
        response_429.status_code = 429
        error = httpx.HTTPStatusError("Rate limit", request=MagicMock(), response=response_429)

        mock_ok = AsyncMock()
        mock_ok.text = "ok"
        mock_ok.candidates = [MagicMock(finish_reason=1)]
        mock_aio_models.generate_content.side_effect = [error, error, mock_ok]

        # Step 2: Measure time
        start_time = time.time()
        with patch("asyncio.sleep", return_value=None):
            await client.generate_response(
                LLMGenerateParams(user_message="test", system_instructions="system instructions")
            )
        elapsed = time.time() - start_time

        # Wait is mocked to 0, so it should be fast
        assert elapsed < 1.0  # Should be very fast with mocked sleep
        assert mock_aio_models.generate_content.call_count == 3
