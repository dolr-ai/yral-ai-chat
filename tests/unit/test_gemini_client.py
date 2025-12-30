"""
Unit tests for GeminiClient retry logic on truncated responses
"""
import pytest
from unittest.mock import MagicMock, patch

from src.services.gemini_client import GeminiClient


class TestGeminiClientRetry:
    """Tests for GeminiClient retry logic when responses are truncated"""

    @pytest.fixture
    def gemini_client(self):
        """Create a GeminiClient instance"""
        with patch('src.services.gemini_client.genai.configure'):
            with patch('src.services.gemini_client.genai.GenerativeModel'):
                client = GeminiClient()
                return client

    def _create_mock_response(self, finish_reason_str, text_content, safety_ratings=None):
        """Helper to create a mock response with specified finish_reason"""
        candidate = MagicMock()
        # Set finish_reason so that str(finish_reason) contains the expected string
        # The code checks: finish_reason_str and "MAX_TOKENS" in finish_reason_str
        # We create a mock object with a custom __str__ method
        finish_reason_mock = MagicMock()
        if finish_reason_str == "MAX_TOKENS":
            finish_reason_mock.__str__ = lambda self: "FinishReason.MAX_TOKENS"
        elif finish_reason_str == "STOP":
            finish_reason_mock.__str__ = lambda self: "STOP"
        elif finish_reason_str == "SAFETY":
            finish_reason_mock.__str__ = lambda self: "SAFETY"
        else:
            finish_reason_mock.__str__ = lambda self: finish_reason_str
        
        candidate.finish_reason = finish_reason_mock
        candidate.safety_ratings = safety_ratings
        response = MagicMock()
        response.candidates = [candidate]
        response.text = text_content
        return response

    @pytest.mark.asyncio
    async def test_retry_on_max_tokens_truncation(self, gemini_client):
        """Test that client retries when response is truncated due to MAX_TOKENS"""
        # Create mock responses: first two truncated, third successful
        truncated_response_1 = self._create_mock_response(
            "MAX_TOKENS",
            "This is a truncated response that was cut off mid-"
        )
        truncated_response_2 = self._create_mock_response(
            "MAX_TOKENS",
            "Another truncated response that got cut"
        )
        success_response = self._create_mock_response(
            "STOP",
            "This is a complete response that finished successfully without truncation."
        )
        
        # Mock the model's generate_content to return truncated, then truncated, then success
        gemini_client.model.generate_content = MagicMock(
            side_effect=[truncated_response_1, truncated_response_2, success_response]
        )
        
        # Call generate_response
        response_text, token_count = await gemini_client.generate_response(
            user_message="Test message",
            system_instructions="You are a helpful assistant."
        )
        
        # Verify it retried (called generate_content 3 times)
        assert gemini_client.model.generate_content.call_count == 3
        
        # Verify it returned the successful (last) response
        assert response_text == "This is a complete response that finished successfully without truncation."
        assert token_count > 0

    @pytest.mark.asyncio
    async def test_retry_all_attempts_truncated_returns_best(self, gemini_client):
        """Test that when all 3 attempts are truncated, it returns the longest response"""
        # Create 3 truncated responses with different lengths
        responses = [
            self._create_mock_response("MAX_TOKENS", "Short"),
            self._create_mock_response("MAX_TOKENS", "This is a longer truncated response"),
            self._create_mock_response("MAX_TOKENS", "Medium length truncated"),
        ]
        
        # Mock the model to return all truncated responses
        gemini_client.model.generate_content = MagicMock(side_effect=responses)
        
        # Call generate_response
        response_text, token_count = await gemini_client.generate_response(
            user_message="Test message",
            system_instructions="You are a helpful assistant."
        )
        
        # Verify it tried 3 times
        assert gemini_client.model.generate_content.call_count == 3
        
        # Verify it returned the longest response (second one)
        assert response_text == "This is a longer truncated response"

    @pytest.mark.asyncio
    async def test_no_retry_on_successful_response(self, gemini_client):
        """Test that successful responses (STOP finish_reason) don't trigger retries"""
        # Create a successful response
        success_response = self._create_mock_response("STOP", "Complete response")
        
        # Mock the model to return successful response
        gemini_client.model.generate_content = MagicMock(return_value=success_response)
        
        # Call generate_response
        response_text, token_count = await gemini_client.generate_response(
            user_message="Test message",
            system_instructions="You are a helpful assistant."
        )
        
        # Verify it only called once (no retries)
        assert gemini_client.model.generate_content.call_count == 1
        
        # Verify it returned the response
        assert response_text == "Complete response"

    @pytest.mark.asyncio
    async def test_retry_on_safety_filter_block(self, gemini_client):
        """Test that safety filter blocks trigger retries"""
        # Create a response blocked by safety filters
        blocked_response = self._create_mock_response("SAFETY", "Partially blocked content")
        success_response = self._create_mock_response("STOP", "Complete safe response")
        
        # Mock the model to return blocked, then success
        gemini_client.model.generate_content = MagicMock(
            side_effect=[blocked_response, success_response]
        )
        
        # Call generate_response
        response_text, token_count = await gemini_client.generate_response(
            user_message="Test message",
            system_instructions="You are a helpful assistant."
        )
        
        # Verify it retried (called twice)
        assert gemini_client.model.generate_content.call_count == 2
        
        # Verify it returned the successful response
        assert response_text == "Complete safe response"

    @pytest.mark.asyncio
    async def test_retry_on_value_error_from_response_text(self, gemini_client):
        """Test that ValueError when accessing response.text triggers retry"""
        # This test verifies that when _generate_content returns was_truncated=True
        # (which happens when response.text raises ValueError), the retry logic kicks in
        
        # Mock _generate_content to return truncated on first call, success on second
        call_count = {'count': 0}
        original_method = gemini_client._generate_content
        
        async def mock_generate_content(contents):
            call_count['count'] += 1
            if call_count['count'] == 1:
                # First call: simulate blocked response (was_truncated=True)
                # This simulates what happens when response.text raises ValueError
                return "", 0.0, True  # (response_text, token_count, was_truncated)
            else:
                # Second call: successful response - call the real method
                return await original_method(contents)
        
        # Replace _generate_content with our mock
        gemini_client._generate_content = mock_generate_content
        
        # Mock the model for successful response
        success_response = self._create_mock_response("STOP", "Complete safe response")
        gemini_client.model.generate_content = MagicMock(return_value=success_response)
        
        # Call generate_response
        response_text, token_count = await gemini_client.generate_response(
            user_message="Test message",
            system_instructions="You are a helpful assistant."
        )
        
        # Verify retry was triggered (called twice: once truncated, once success)
        assert call_count['count'] == 2
        
        # Verify it returned the successful response
        assert response_text == "Complete safe response"
