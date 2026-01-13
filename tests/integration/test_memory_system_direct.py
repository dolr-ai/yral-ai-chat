
from unittest.mock import AsyncMock

import pytest
from fastapi import BackgroundTasks

from src.db.repositories import ConversationRepository, InfluencerRepository, MessageRepository
from src.services.chat_service import ChatService
from src.services.gemini_client import GeminiClient
from src.services.openrouter_client import OpenRouterClient
from src.services.storage_service import StorageService


@pytest.mark.asyncio
async def test_chat_service_memory_background_task_direct(test_influencer_id):
    """
    Integration test calling ChatService functions directly.
    Verifies that the background task is correctly added and updates the DB.
    """
    # 1. Setup real repositories (using the test database initialized in conftest)
    influencer_repo = InfluencerRepository()
    conversation_repo = ConversationRepository()
    message_repo = MessageRepository()
    storage_service = StorageService()
    
    # 2. Setup Mock AI Clients (to avoid external network calls)
    mock_gemini = AsyncMock(spec=GeminiClient)
    mock_gemini.generate_response = AsyncMock(return_value=("Direct function response", 15))
    
    test_memory = {"favorite_color": "blue"}
    mock_gemini.extract_memories = AsyncMock(return_value=test_memory)
    
    # 3. Initialize ChatService with real repos but mocked AI
    service = ChatService(
        gemini_client=mock_gemini,
        influencer_repo=influencer_repo,
        conversation_repo=conversation_repo,
        message_repo=message_repo,
        storage_service=storage_service,
        openrouter_client=AsyncMock(spec=OpenRouterClient)
    )
    
    user_id = "direct-test-user"
    
    # 4. Create a real conversation via the service
    conv, is_new = await service.create_conversation(user_id, test_influencer_id)
    assert conv.id is not None
    
    # 5. Create a real BackgroundTasks object (from FastAPI)
    bg_tasks = BackgroundTasks()
    
    # 6. Call send_message directly
    # This should add a task to bg_tasks
    from src.models.entities import MessageType
    await service.send_message(
        conversation_id=conv.id,
        user_id=user_id,
        content="I really like the color blue.",
        message_type=MessageType.TEXT,
        background_tasks=bg_tasks
    )
    
    # 7. Check that a task was indeed added
    assert len(bg_tasks.tasks) == 1
    
    # 8. MANUALLY execute the background task
    # This mimics what FastAPI does after sending the response
    task = bg_tasks.tasks[0]
    # task.func is self._update_conversation_memories
    # task.args / task.kwargs are the arguments
    await task.func(*task.args, **task.kwargs)
    
    # 9. Verify the database state
    updated_conv = await conversation_repo.get_by_id(conv.id)
    assert updated_conv.metadata["memories"] == test_memory
    
    # 10. Final check: AI was called correctly
    mock_gemini.generate_response.assert_called_once()
    mock_gemini.extract_memories.assert_called_once()
