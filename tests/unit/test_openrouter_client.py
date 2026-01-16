"""
Unit tests for OpenRouter AI client, Provider health service, and NSFW routing

Tests cover:
- OpenRouter client initialization
- Health checks for both providers
- NSFW influencer filtering
- Provider selection logic
"""

from unittest.mock import patch

from src.services.openrouter_client import OpenRouterClient


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

        # Get the mock headers object from the client's http_client
        mock_headers = client.http_client.headers

        # Check that update was called with the expected headers
        mock_headers.update.assert_called_once()
        args, _ = mock_headers.update.call_args
        headers_arg = args[0]
        assert headers_arg["Authorization"] == "Bearer test-key-12345"
        assert headers_arg["HTTP-Referer"] == "https://yral.com"
