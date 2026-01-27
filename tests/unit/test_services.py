"""
Simplified unit tests for core services.
We prioritize clarity and explicit setup over conciseness.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.exceptions import BadRequestException, NotFoundException
from src.models.internal import AIResponse, SendMessageParams
from src.services.chat_service import ChatService
from src.services.influencer_service import InfluencerService
from src.services.storage_service import StorageService

# ============================================================================
# InfluencerService Tests
# ============================================================================


class TestInfluencerService:
    @pytest.fixture
    def mock_repo(self):
        """Standard mock repository for influencers"""
        return MagicMock()

    @pytest.fixture
    def service(self, mock_repo):
        """The service being tested"""
        return InfluencerService(mock_repo)

    @pytest.mark.asyncio
    async def test_get_influencer_returns_correct_data(self, service, mock_repo, sample_influencer):
        """
        GIVEN a valid influencer ID
        WHEN the repository finds the influencer
        THEN the service should return that exact influencer
        """
        # Step 1: Tell the mock repo what to return
        mock_repo.get_with_conversation_count = AsyncMock(return_value=sample_influencer)

        # Step 2: Call the service
        result = await service.get_influencer(sample_influencer.id)

        # Step 3: Verify the result is what we expected
        assert result.id == sample_influencer.id
        assert result.display_name == sample_influencer.display_name

        # Step 4: Verify the repository was actually called with the right ID
        mock_repo.get_with_conversation_count.assert_called_once_with(sample_influencer.id)

    @pytest.mark.asyncio
    async def test_get_influencer_raises_error_when_missing(self, service, mock_repo):
        """
        GIVEN an influencer ID that doesn't exist
        WHEN we try to get it
        THEN the service should raise a NotFoundException
        """
        # Step 1: Mock the repo to return None (not found)
        mock_repo.get_with_conversation_count = AsyncMock(return_value=None)

        # Step 2: Assert that the specific exception is raised
        with pytest.raises(NotFoundException, match="Influencer not found"):
            await service.get_influencer("non-existent-id")

    @pytest.mark.asyncio
    async def test_list_influencers_shows_correct_count(self, service, mock_repo, sample_influencer):
        """
        GIVEN one influencer exists in the database
        WHEN we list all influencers
        THEN we should get a list containing that one influencer
        """
        # Step 1: Setup mock data
        influencers_list = [sample_influencer]
        mock_repo.list_all = AsyncMock(return_value=influencers_list)
        mock_repo.count_all = AsyncMock(return_value=1)

        # Step 2: Call the service
        items, total_count = await service.list_influencers(limit=10)

        # Step 3: Verify output
        assert len(items) == 1
        # Step 3: Verify output
        assert len(items) == 1
        assert items[0].id == sample_influencer.id
        assert total_count == 1

    @pytest.mark.asyncio
    async def test_create_influencer_clears_cache(self, service, mock_repo, sample_influencer):
        """
        GIVEN a new influencer request
        WHEN we create the influencer
        THEN the repository should create it AND the service should invalidate caches
        """
        # Step 1: Mock setup
        mock_repo.create = AsyncMock(return_value=sample_influencer)
        
        # Replace the whole method on the instance with a Mock object to verify invalidation
        service.list_influencers = MagicMock()
        service.list_influencers.invalidate_all = MagicMock()

        service.list_nsfw_influencers = MagicMock()
        service.list_nsfw_influencers.invalidate_all = MagicMock()

        # Step 2: Call create
        result = await service.create_influencer(sample_influencer)

        # Step 3: Verify creation
        mock_repo.create.assert_called_once_with(sample_influencer)
        assert result == sample_influencer

        # Step 4: Verify cache invalidation
        # Since sample_influencer.is_nsfw is False (from fixture), only list_influencers should be cleared
        service.list_influencers.invalidate_all.assert_called_once()
        service.list_nsfw_influencers.invalidate_all.assert_not_called()


# ============================================================================
# StorageService Tests
# ============================================================================


class TestStorageService:
    @pytest.fixture
    def service(self):
        """Storage service with a mocked aioboto3 session"""
        with patch("src.services.storage_service.aioboto3.Session"):
            return StorageService()

    @pytest.mark.asyncio
    async def test_save_file_generates_correct_key(self, service):
        """
        WHEN we save a file
        THEN it should generate an S3 key, presigned URL, and upload via http
        """
        # Step 1: Mock setup for async context manager (S3)
        mock_s3 = AsyncMock()
        mock_s3.generate_presigned_url.return_value = "https://fake-s3.com/upload"
        
        service.get_s3_client = AsyncMock(return_value=MagicMock(
            __aenter__=AsyncMock(return_value=mock_s3),
            __aexit__=AsyncMock()
        ))
        service.bucket = "test-bucket"
        
        # Mock aiohttp (Context Managers galore!)
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text.return_value = "OK"
        
        # Mock the response context manager
        mock_put_ctx = MagicMock()
        mock_put_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_put_ctx.__aexit__ = AsyncMock(return_value=None)
        
        # Mock the session object
        mock_session = MagicMock()
        mock_session.put.return_value = mock_put_ctx
        
        # Mock the session context manager constructor
        mock_session_ctx = MagicMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)

        # Fix the UUID so we know what to expect in the assertion
        with patch("src.services.storage_service.uuid4", return_value="fixed-uuid"), \
             patch("src.services.storage_service.aiohttp.ClientSession", return_value=mock_session_ctx):
            
            file_data = b"some-content"
            filename = "photo.jpg"
            user_id = "user-123"

            # Step 2: Run the save
            key, mime, size = await service.save_file(file_data, filename, user_id)

            # Step 3: Verify the internal logic
            assert key == "user-123/fixed-uuid.jpg"
            assert mime == "image/jpeg"
            assert size == len(file_data)
            
            # Step 4: Verify S3 presign generation
            mock_s3.generate_presigned_url.assert_called_once()
            
            # Step 5: Verify HTTP upload
            mock_session.put.assert_called_once_with(
                "https://fake-s3.com/upload",
                data=file_data,
                headers={"Content-Type": "image/jpeg", "Content-Length": str(len(file_data))}
            )


    def test_validate_image_rejects_non_image_files(self, service):
        """
        WHEN we try to validate an executable file as an image
        THEN it should raise an 'Unsupported image format' error
        """
        with pytest.raises(BadRequestException, match="Unsupported image format"):
            service.validate_image("malicious.exe", 1024)

    def test_validate_image_rejects_massive_files(self, service):
        """
        WHEN a file is larger than allowed
        THEN it should raise an 'Image too large' error
        """
        with patch("src.services.storage_service.settings") as mock_settings:
            mock_settings.max_image_size_bytes = 100  # Tiny limit for testing

            with pytest.raises(BadRequestException, match="Image too large"):
                service.validate_image("big.png", 500)  # 500 > 100


# ============================================================================
# ChatService Tests
# ============================================================================


class TestChatService:
    @pytest.fixture
    def mock_repos(self):
        """Group of mocked repositories needed by ChatService"""
        return {"influencer": MagicMock(), "conversation": MagicMock(), "message": MagicMock()}

    @pytest.fixture
    def service(self, mock_repos):
        """Chat service with all its dependencies mocked out"""
        return ChatService(
            gemini_client=MagicMock(),
            influencer_repo=mock_repos["influencer"],
            conversation_repo=mock_repos["conversation"],
            message_repo=mock_repos["message"],
            storage_service=MagicMock(),
            openrouter_client=MagicMock(),
        )

    @pytest.mark.asyncio
    async def test_create_conversation_works_for_new_users(
        self, service, mock_repos, sample_influencer, sample_conversation
    ):
        """
        GIVEN a user who hasn't talked to an influencer yet
        WHEN a conversation is created
        THEN a new conversation record should be made in the DB
        """
        # Step 1: Define what happens when we check for existing conversations
        mock_repos["influencer"].get_by_id = AsyncMock(return_value=sample_influencer)
        mock_repos["conversation"].get_existing = AsyncMock(return_value=None)  # No existing
        mock_repos["conversation"].create = AsyncMock(return_value=sample_conversation)
        mock_repos["message"].create = AsyncMock() # Required for initial greeting

        # Step 2: Run the service logic
        conv, is_new = await service.create_conversation("user-456", sample_influencer.id)

        # Step 3: Verify the result
        assert conv.id == sample_conversation.id
        assert is_new is True

        # Step 4: Ensure create was actually called
        mock_repos["conversation"].create.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_message_triggers_ai_and_background_memory_save(
        self, service, mock_repos, sample_influencer, sample_conversation, sample_message
    ):
        """
        GIVEN an existing conversation
        WHEN a user sends a message
        THEN the AI should respond AND a background task should be scheduled to update memories
        """
        # Step 1: Setup the environment mocks
        mock_repos["influencer"].get_by_id = AsyncMock(return_value=sample_influencer)
        mock_repos["conversation"].get_by_id = AsyncMock(return_value=sample_conversation)
        mock_repos["message"].create = AsyncMock(return_value=sample_message)
        mock_repos["message"].get_recent_for_context = AsyncMock(return_value=[])

        # Mock the AI Client response
        service.gemini_client.generate_response = AsyncMock(return_value=AIResponse(text="Hi there!", token_count=50))

        # Step 2: Mock BackgroundTasks (FastAPI)
        mock_background = MagicMock()

        # Step 3: Run the service
        await service.send_message(
            SendMessageParams(
                conversation_id=sample_conversation.id,
                user_id=sample_conversation.user_id,
                content="Hello",
                background_tasks=mock_background,
            )
        )

        # Step 4: Verify the interaction
        # We expect the AI to have been called
        service.gemini_client.generate_response.assert_called_once()

        # We expect a background task to be added for memory extraction
        mock_background.add_task.assert_called_once()
        # Verify it's calling the memory update internal function
        assert mock_background.add_task.call_args[0][0] == service._update_conversation_memories
