
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.entities import MessageType
from src.services.chat_service import ChatService


# Simple in-memory fake for RedisCache to avoid external dependency issues in tests
class FakeCache:
    def __init__(self):
        self.store = {}

    async def lpush(self, key: str, *values):
        if key not in self.store:
            self.store[key] = []
        # Redis LPUSH prepends. Arguments are pushed in order.
        # LPUSH key a b c -> [c, b, a, ...]
        # So we reverse values and insert at 0
        for v in values:
            self.store[key].insert(0, v)

    async def lrange(self, key: str, start: int, end: int):
        if key not in self.store:
            return []
        # Redis lrange is inclusive, python slice is exclusive
        # and Redis end=-1 means end.
        if end == -1:
            return self.store[key][start:]
        return self.store[key][start:end+1]

    async def expire(self, key: str, ttl: int):
        pass
    
    async def delete(self, key: str):
        if key in self.store:
            del self.store[key]

@pytest.mark.asyncio
async def test_race_condition_immediate_follow_up(test_influencer_id):
    """
    Simulate a race condition where a user sends a message, and immediately sends another 
    before the first one is persisted to DB.
    
    The Write-Through Cache should resolve this.
    """
    conversation_id = "race-cond-conv-id"
    user_id = "race-cond-user"
    
    # Setup Fake Cache
    fake_cache = FakeCache()

    # Mock Repositories
    mock_influencer_repo = AsyncMock()
    mock_influencer = MagicMock()
    mock_influencer.id = test_influencer_id
    mock_influencer.is_nsfw = False
    mock_influencer.system_instructions = "You are a helpful bot."
    mock_influencer_repo.get_by_id.return_value = mock_influencer
    
    mock_conversation_repo = AsyncMock()
    mock_conv = MagicMock()
    mock_conv.id = conversation_id
    mock_conv.user_id = user_id
    mock_conv.influencer_id = test_influencer_id
    mock_conversation_repo.get_by_id.return_value = mock_conv
    
    mock_message_repo = AsyncMock()
    mock_message_repo.get_recent_for_context.return_value = []
    
    
    # Mock AI Client
    mock_gemini = AsyncMock()
    mock_gemini.generate_response.return_value = ("AI Response 1", 10)
    
    # Initialize Service WITH PATCHED CACHE
    with patch("src.services.chat_service.cache", fake_cache):
        service = ChatService(
            gemini_client=mock_gemini,
            influencer_repo=mock_influencer_repo,
            conversation_repo=mock_conversation_repo,
            message_repo=mock_message_repo,
            storage_service=AsyncMock(),
            openrouter_client=AsyncMock()
        )
        
        # Send Message 1
        mock_bg_tasks = MagicMock()
        
        await service.send_message(
            conversation_id=conversation_id,
            user_id=user_id,
            content="Message 1 (Race Start)",
            message_type=MessageType.TEXT,
            background_tasks=mock_bg_tasks
        )
        
        # VERIFY 1: Cache should have M1 and AI1
        cache_key = f"conversation:{conversation_id}:messages"
        cached_msgs = await fake_cache.lrange(cache_key, 0, 10)
        assert len(cached_msgs) == 2
        assert cached_msgs[1].content == "Message 1 (Race Start)"
        assert cached_msgs[0].content == "AI Response 1"
        
        # Send Message 2 (IMMEDIATE FOLLOW UP)
        mock_gemini.generate_response.reset_mock()
        mock_gemini.generate_response.return_value = ("AI Response 2", 10)
        
        await service.send_message(
            conversation_id=conversation_id,
            user_id=user_id,
            content="Message 2 (Follow Up)",
            message_type=MessageType.TEXT,
            background_tasks=mock_bg_tasks
        )
        
        
        # VERIFY 2: The AI call for Message 2 should have received Message 1 in its history
        call_args = mock_gemini.generate_response.call_args
        history_passed_to_ai = call_args.kwargs["conversation_history"]
        
        assert len(history_passed_to_ai) == 2
        assert history_passed_to_ai[0].content == "Message 1 (Race Start)"
        assert history_passed_to_ai[1].content == "AI Response 1"
        
        # VERIFY 3: Cache should now have 4 messages
        cached_msgs_updated = await fake_cache.lrange(cache_key, 0, 10)
        assert len(cached_msgs_updated) == 4
        assert cached_msgs_updated[0].content == "AI Response 2"
        assert cached_msgs_updated[1].content == "Message 2 (Follow Up)"
