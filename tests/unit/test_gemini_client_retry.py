"""
Unit tests for Gemini client retry logic with exponential backoff
"""
import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from loguru import logger

from src.services.gemini_client import GeminiClient, _is_retryable_http_error


class TestRetryableErrorDetection:
    """Test the retryable error detection function"""

    def test_retry_on_http_429(self):
        """Test that HTTP 429 (rate limit) is retryable"""
        response = MagicMock()
        response.status_code = 429
        error = httpx.HTTPStatusError("Rate limited", request=MagicMock(), response=response)
        assert _is_retryable_http_error(error) is True

    def test_retry_on_http_500(self):
        """Test that HTTP 500 (server error) is retryable"""
        response = MagicMock()
        response.status_code = 500
        error = httpx.HTTPStatusError("Server error", request=MagicMock(), response=response)
        assert _is_retryable_http_error(error) is True

    def test_retry_on_http_503(self):
        """Test that HTTP 503 (service unavailable) is retryable"""
        response = MagicMock()
        response.status_code = 503
        error = httpx.HTTPStatusError("Service unavailable", request=MagicMock(), response=response)
        assert _is_retryable_http_error(error) is True

    def test_no_retry_on_http_400(self):
        """Test that HTTP 400 (bad request) is not retryable"""
        response = MagicMock()
        response.status_code = 400
        error = httpx.HTTPStatusError("Bad request", request=MagicMock(), response=response)
        assert _is_retryable_http_error(error) is False

    def test_no_retry_on_http_401(self):
        """Test that HTTP 401 (unauthorized) is not retryable"""
        response = MagicMock()
        response.status_code = 401
        error = httpx.HTTPStatusError("Unauthorized", request=MagicMock(), response=response)
        assert _is_retryable_http_error(error) is False

    def test_retry_on_connection_error(self):
        """Test that ConnectionError is retryable"""
        error = httpx.ConnectError("Connection failed")
        assert _is_retryable_http_error(error) is True

    def test_retry_on_timeout_error(self):
        """Test that TimeoutError is retryable"""
        error = httpx.TimeoutException("Request timeout")
        assert _is_retryable_http_error(error) is True

    def test_retry_on_request_error(self):
        """Test that RequestError is retryable"""
        error = httpx.RequestError("Request failed")
        assert _is_retryable_http_error(error) is True

    def test_retry_on_error_with_status_code_attribute(self):
        """Test that errors with status_code attribute are checked"""
        error = MagicMock()
        error.status_code = 429
        assert _is_retryable_http_error(error) is True

        error.status_code = 500
        assert _is_retryable_http_error(error) is True

        error.status_code = 400
        assert _is_retryable_http_error(error) is False

    def test_retry_on_error_message_patterns(self):
        """Test that error messages with retryable patterns are detected"""
        error = Exception("Rate limit exceeded")
        assert _is_retryable_http_error(error) is True

        error = Exception("Service unavailable")
        assert _is_retryable_http_error(error) is True

        error = Exception("Network timeout")
        assert _is_retryable_http_error(error) is True

        error = Exception("Connection refused")
        assert _is_retryable_http_error(error) is True

        error = Exception("Invalid request")
        assert _is_retryable_http_error(error) is False


class TestGeminiClientRetry:
    """Test retry logic in Gemini client methods"""

    @pytest.fixture(scope="function")
    def gemini_client(self):
        """Create a GeminiClient instance with mocked dependencies"""
        with patch("src.services.gemini_client.genai.Client") as mock_client_class, \
             patch("src.services.gemini_client.settings") as mock_settings:
            
            mock_settings.gemini_api_key = "test-api-key"
            mock_settings.gemini_model = "gemini-2.5-flash"
            mock_settings.gemini_max_tokens = 2048
            mock_settings.gemini_temperature = 0.7
            
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            
            mock_aio_models = AsyncMock()
            mock_client.aio = MagicMock()
            mock_client.aio.models = mock_aio_models
            
            client = GeminiClient()
            client.http_client = AsyncMock()
            client._mock_aio_models = mock_aio_models
            
            yield client

    @pytest.mark.asyncio
    async def test_generate_content_retries_on_rate_limit(self, gemini_client):
        """Test that _generate_content retries on rate limit (429)"""
        mock_aio_models = gemini_client._mock_aio_models
        
        mock_response = MagicMock()
        mock_response.text = "Test response"
        mock_response.candidates = [MagicMock(finish_reason=1)]
        
        response_429 = httpx.HTTPStatusError(
            "Rate limited",
            request=MagicMock(),
            response=MagicMock(status_code=429)
        )
        
        mock_aio_models.generate_content.side_effect = [
            response_429,
            response_429,
            mock_response
        ]
        
        result = await gemini_client._generate_content([{"role": "user", "parts": [{"text": "test"}]}])
        
        assert result[0] == "Test response"
        assert mock_aio_models.generate_content.call_count == 3

    @pytest.mark.asyncio
    async def test_generate_content_retries_on_server_error(self, gemini_client):
        """Test that _generate_content retries on server error (500)"""
        mock_aio_models = gemini_client._mock_aio_models
        
        mock_response = MagicMock()
        mock_response.text = "Success after retry"
        mock_response.candidates = [MagicMock(finish_reason=1)]
        
        response_500 = httpx.HTTPStatusError(
            "Server error",
            request=MagicMock(),
            response=MagicMock(status_code=500)
        )
        
        mock_aio_models.generate_content.side_effect = [
            response_500,
            mock_response
        ]
        
        result = await gemini_client._generate_content([{"role": "user", "parts": [{"text": "test"}]}])
        
        assert result[0] == "Success after retry"
        assert mock_aio_models.generate_content.call_count == 2

    @pytest.mark.asyncio
    async def test_generate_content_retries_on_connection_error(self, gemini_client):
        """Test that _generate_content retries on connection error"""
        mock_aio_models = gemini_client._mock_aio_models
        
        mock_response = MagicMock()
        mock_response.text = "Connected"
        mock_response.candidates = [MagicMock(finish_reason=1)]
        
        connection_error = ConnectionError("Connection failed")
        
        mock_aio_models.generate_content.side_effect = [
            connection_error,
            connection_error,
            mock_response
        ]
        
        result = await gemini_client._generate_content([{"role": "user", "parts": [{"text": "test"}]}])
        
        assert result[0] == "Connected"
        assert mock_aio_models.generate_content.call_count == 3

    @pytest.mark.asyncio
    async def test_generate_content_no_retry_on_client_error(self, gemini_client):
        """Test that _generate_content does not retry on client errors (400)"""
        mock_aio_models = gemini_client._mock_aio_models
        
        response_400 = httpx.HTTPStatusError(
            "Bad request",
            request=MagicMock(),
            response=MagicMock(status_code=400)
        )
        
        mock_aio_models.generate_content.side_effect = response_400
        
        with pytest.raises(httpx.HTTPStatusError):
            await gemini_client._generate_content([{"role": "user", "parts": [{"text": "test"}]}])
        
        assert mock_aio_models.generate_content.call_count == 1

    @pytest.mark.asyncio
    async def test_generate_content_exponential_backoff(self, gemini_client):
        """Test that exponential backoff is used between retries"""
        mock_aio_models = gemini_client._mock_aio_models
        
        mock_response = MagicMock()
        mock_response.text = "Success"
        mock_response.candidates = [MagicMock(finish_reason=1)]
        
        timeout_error = TimeoutError("Timeout")
        
        mock_aio_models.generate_content.side_effect = [
            timeout_error,
            timeout_error,
            mock_response
        ]
        
        start_time = time.time()
        await gemini_client._generate_content([{"role": "user", "parts": [{"text": "test"}]}])
        elapsed = time.time() - start_time
        
        assert elapsed >= 2.5
        assert mock_aio_models.generate_content.call_count == 3

    @pytest.mark.asyncio
    async def test_generate_content_max_retries_exceeded(self, gemini_client):
        """Test that after max retries, exception is raised"""
        mock_aio_models = gemini_client._mock_aio_models
        
        timeout_error = TimeoutError("Timeout")
        
        mock_aio_models.generate_content.side_effect = timeout_error
        
        with pytest.raises(TimeoutError):
            await gemini_client._generate_content([{"role": "user", "parts": [{"text": "test"}]}])
        
        assert mock_aio_models.generate_content.call_count == 3

    @pytest.mark.asyncio
    async def test_transcribe_audio_retries(self, gemini_client):
        """Test that transcribe_audio retries on errors"""
        mock_aio_models = gemini_client._mock_aio_models
        
        gemini_client._download_audio = AsyncMock(return_value={"mime_type": "audio/mpeg", "data": b"audio"})
        
        mock_response = MagicMock()
        mock_response.text = "Transcribed text"
        
        response_503 = httpx.HTTPStatusError(
            "Service unavailable",
            request=MagicMock(),
            response=MagicMock(status_code=503)
        )
        
        mock_aio_models.generate_content.side_effect = [
            response_503,
            mock_response
        ]
        
        result = await gemini_client.transcribe_audio("http://example.com/audio.mp3")
        
        assert result == "Transcribed text"
        assert mock_aio_models.generate_content.call_count == 2

    @pytest.mark.asyncio
    async def test_extract_memories_retries(self, gemini_client):
        """Test that extract_memories retries on errors"""
        mock_aio_models = gemini_client._mock_aio_models
        
        mock_response = MagicMock()
        mock_response.text = '{"name": "John", "age": "30"}'
        
        connection_error = ConnectionError("Connection failed")
        
        mock_aio_models.generate_content.side_effect = [
            connection_error,
            mock_response
        ]
        
        result = await gemini_client.extract_memories("Hello", "Hi there", {})
        
        assert "name" in result
        assert result["name"] == "John"
        assert mock_aio_models.generate_content.call_count == 2

    @pytest.mark.asyncio
    async def test_health_check_retries(self, gemini_client):
        """Test that health_check retries on errors"""
        mock_aio_models = gemini_client._mock_aio_models
        
        mock_response = MagicMock()
        mock_response.text = "Hi"
        
        timeout_error = TimeoutError("Timeout")
        
        mock_aio_models.generate_content.side_effect = [
            timeout_error,
            mock_response
        ]
        
        result = await gemini_client.health_check()
        
        assert result.status == "up"
        assert result.latency_ms is not None
        assert mock_aio_models.generate_content.call_count == 2

    @pytest.mark.asyncio
    async def test_health_check_fails_after_max_retries(self, gemini_client):
        """Test that health_check returns down status after max retries"""
        mock_aio_models = gemini_client._mock_aio_models
        
        timeout_error = TimeoutError("Timeout")
        
        mock_aio_models.generate_content.side_effect = timeout_error
        
        result = await gemini_client.health_check()
        
        assert result.status == "down"
        assert result.error is not None
        assert result.latency_ms is None
        assert mock_aio_models.generate_content.call_count == 3

    @pytest.mark.asyncio
    async def test_success_on_first_attempt_no_retry(self, gemini_client):
        """Test that successful calls don't trigger retries"""
        mock_aio_models = gemini_client._mock_aio_models
        
        mock_response = MagicMock()
        mock_response.text = "Success"
        mock_response.candidates = [MagicMock(finish_reason=1)]
        
        mock_aio_models.generate_content.return_value = mock_response
        
        result = await gemini_client._generate_content([{"role": "user", "parts": [{"text": "test"}]}])
        
        assert result[0] == "Success"
        assert mock_aio_models.generate_content.call_count == 1

    @pytest.mark.asyncio
    async def test_retry_logs_warnings(self, gemini_client):
        """Test that retry attempts are logged"""
        mock_aio_models = gemini_client._mock_aio_models
        
        mock_response = MagicMock()
        mock_response.text = "Success"
        mock_response.candidates = [MagicMock(finish_reason=1)]
        
        timeout_error = TimeoutError("Timeout")
        
        mock_aio_models.generate_content.side_effect = [
            timeout_error,
            mock_response
        ]
        
        log_messages = []
        
        def capture_log(message):
            log_messages.append(str(message))
        
        handler_id = logger.add(capture_log, level="WARNING", format="{message}")
        
        try:
            await gemini_client._generate_content([{"role": "user", "parts": [{"text": "test"}]}])
        finally:
            logger.remove(handler_id)
        
        log_text = " ".join(log_messages).lower()
        assert "retry" in log_text or "sleeping" in log_text or "retrying" in log_text, \
            f"Expected retry log message, but got: {log_messages}"

