"""
Simplified unit tests for provider selection and NSFW routing.
We focus on making the decision logic transparent.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.chat_service import ChatService
from src.services.influencer_service import InfluencerService


class TestProviderRouting:
    """Test which AI client is chosen based on NSFW status"""

    @pytest.fixture
    def chat_service(self):
        """ChatService with mocked dependencies"""
        return ChatService(
            gemini_client=MagicMock(),
            influencer_repo=MagicMock(),
            conversation_repo=MagicMock(),
            message_repo=MagicMock(),
            storage_service=MagicMock(),
            openrouter_client=MagicMock(),
        )

    def test_routing_uses_openrouter_for_nsfw_content(self, chat_service):
        """
        WHEN content is marked as NSFW
        THEN ChatService should select the OpenRouter client
        """
        selected_client = chat_service._select_ai_client(is_nsfw=True)
        assert selected_client == chat_service.openrouter_client

    def test_routing_uses_gemini_for_safe_content(self, chat_service):
        """
        WHEN content is safe (not NSFW)
        THEN ChatService should select the Gemini client
        """
        selected_client = chat_service._select_ai_client(is_nsfw=False)
        assert selected_client == chat_service.gemini_client

    def test_fallback_to_gemini_if_openrouter_is_not_configured(self, chat_service):
        """
        GIVEN OpenRouter is not available (null)
        WHEN we try to get an NSFW provider
        THEN it should fallback to Gemini instead of crashing
        """
        chat_service.openrouter_client = None
        selected_client = chat_service._select_ai_client(is_nsfw=True)
        assert selected_client == chat_service.gemini_client


class TestInfluencerNSFWLogic:
    """Test how InfluencerService identifies NSFW providers"""

    @pytest.fixture
    def service(self):
        """InfluencerService with a mocked repo"""
        return InfluencerService(AsyncMock())

    @pytest.mark.asyncio
    async def test_get_openrouter_name_for_nsfw_influencer(self, service, sample_influencer):
        """
        VERIFY that an NSFW influencer correctly identifies 'openrouter' as its provider
        """
        sample_influencer.is_nsfw = True
        provider_name = await service.get_ai_provider_for_influencer(sample_influencer)
        assert provider_name == "openrouter"

    @pytest.mark.asyncio
    async def test_get_gemini_name_for_safe_influencer(self, service, sample_influencer):
        """
        VERIFY that a safe influencer correctly identifies 'gemini' as its provider
        """
        sample_influencer.is_nsfw = False
        provider_name = await service.get_ai_provider_for_influencer(sample_influencer)
        assert provider_name == "gemini"
