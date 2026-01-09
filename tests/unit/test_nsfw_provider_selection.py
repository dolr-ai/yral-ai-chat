"""
Unit tests for provider selection logic and NSFW routing

Tests cover:
- Provider selection based on is_nsfw flag
- ChatService routing to correct client
- InfluencerService NSFW methods
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models.entities import AIInfluencer


class TestProviderSelection:
    """Test provider selection logic"""

    def test_select_openrouter_for_nsfw_influencer(self):
        """Test that NSFW influencers use OpenRouter"""
        from src.services.chat_service import ChatService

        # Mock both clients
        mock_gemini = MagicMock()
        mock_openrouter = MagicMock()
        mock_influencer_repo = MagicMock()
        mock_conversation_repo = MagicMock()
        mock_message_repo = MagicMock()
        mock_storage_service = MagicMock()

        service = ChatService(
            gemini_client=mock_gemini,
            influencer_repo=mock_influencer_repo,
            conversation_repo=mock_conversation_repo,
            message_repo=mock_message_repo,
            storage_service=mock_storage_service,
            openrouter_client=mock_openrouter,
        )

        # Test selection with NSFW flag
        selected_client = service._select_ai_client(is_nsfw=True)

        assert selected_client == mock_openrouter

    def test_select_gemini_for_regular_influencer(self):
        """Test that regular influencers use Gemini"""
        from src.services.chat_service import ChatService

        mock_gemini = MagicMock()
        mock_openrouter = MagicMock()
        mock_influencer_repo = MagicMock()
        mock_conversation_repo = MagicMock()
        mock_message_repo = MagicMock()
        mock_storage_service = MagicMock()

        service = ChatService(
            gemini_client=mock_gemini,
            influencer_repo=mock_influencer_repo,
            conversation_repo=mock_conversation_repo,
            message_repo=mock_message_repo,
            storage_service=mock_storage_service,
            openrouter_client=mock_openrouter,
        )

        # Test selection without NSFW flag
        selected_client = service._select_ai_client(is_nsfw=False)

        assert selected_client == mock_gemini

    def test_select_gemini_when_openrouter_unavailable(self):
        """Test fallback to Gemini when OpenRouter is not configured"""
        from src.services.chat_service import ChatService

        mock_gemini = MagicMock()
        mock_influencer_repo = MagicMock()
        mock_conversation_repo = MagicMock()
        mock_message_repo = MagicMock()
        mock_storage_service = MagicMock()

        service = ChatService(
            gemini_client=mock_gemini,
            influencer_repo=mock_influencer_repo,
            conversation_repo=mock_conversation_repo,
            message_repo=mock_message_repo,
            storage_service=mock_storage_service,
            openrouter_client=None,  # Not configured
        )

        # Even with NSFW flag, should fall back to Gemini
        selected_client = service._select_ai_client(is_nsfw=True)

        assert selected_client == mock_gemini


class TestInfluencerServiceNSFW:
    """Test InfluencerService NSFW methods"""

    @pytest.mark.asyncio
    async def test_is_nsfw_method_exists(self):
        """Test that InfluencerService has is_nsfw method"""
        from src.services.influencer_service import InfluencerService

        mock_repository = AsyncMock()
        mock_repository.is_nsfw = AsyncMock(return_value=True)

        service = InfluencerService(mock_repository)

        # Test method exists and works
        result = await service.is_nsfw("test-id")

        assert result is True
        mock_repository.is_nsfw.assert_called_once_with("test-id")

    @pytest.mark.asyncio
    async def test_list_nsfw_influencers_method(self):
        """Test that InfluencerService can list NSFW influencers"""
        from src.services.influencer_service import InfluencerService

        mock_influencer1 = MagicMock(spec=AIInfluencer)
        mock_influencer1.name = "savita_bhabhi"
        mock_influencer1.is_nsfw = True

        mock_influencer2 = MagicMock(spec=AIInfluencer)
        mock_influencer2.name = "other_nsfw"
        mock_influencer2.is_nsfw = True

        mock_influencers = [mock_influencer1, mock_influencer2]
        mock_influencers = [mock_influencer1, mock_influencer2]

        mock_repository = AsyncMock()
        mock_repository.list_nsfw = AsyncMock(return_value=mock_influencers)
        mock_repository.count_nsfw = AsyncMock(return_value=2)

        service = InfluencerService(mock_repository)

        result, total = await service.list_nsfw_influencers(limit=50, offset=0)

        assert len(result) == 2
        assert total == 2
        mock_repository.list_nsfw.assert_called_once_with(limit=50, offset=0)

    @pytest.mark.asyncio
    async def test_get_ai_provider_for_influencer(self):
        """Test getting correct AI provider for influencer"""
        from src.services.influencer_service import InfluencerService

        mock_influencer = MagicMock(spec=AIInfluencer)
        mock_influencer.is_nsfw = True

        mock_repository = AsyncMock()

        service = InfluencerService(mock_repository)

        provider = await service.get_ai_provider_for_influencer(mock_influencer)

        assert provider == "openrouter"

    @pytest.mark.asyncio
    async def test_get_ai_provider_for_regular_influencer(self):
        """Test getting AI provider for regular influencer"""
        from src.services.influencer_service import InfluencerService

        mock_influencer = MagicMock(spec=AIInfluencer)
        mock_influencer.is_nsfw = False

        mock_repository = AsyncMock()

        service = InfluencerService(mock_repository)

        provider = await service.get_ai_provider_for_influencer(mock_influencer)

        assert provider == "gemini"


class TestNSFWDatabaseQueryies:
    """Test NSFW-related database queries"""

    def test_is_nsfw_query_exists(self):
        """Test that repository has is_nsfw query method"""
        from src.db.repositories.influencer_repository import InfluencerRepository

        # Verify method exists
        assert hasattr(InfluencerRepository, "is_nsfw")

    def test_list_nsfw_query_exists(self):
        """Test that repository has list_nsfw query method"""
        from src.db.repositories.influencer_repository import InfluencerRepository

        # Verify method exists
        assert hasattr(InfluencerRepository, "list_nsfw")

    def test_count_nsfw_query_exists(self):
        """Test that repository has count_nsfw query method"""
        from src.db.repositories.influencer_repository import InfluencerRepository

        # Verify method exists
        assert hasattr(InfluencerRepository, "count_nsfw")
