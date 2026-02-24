from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import Response

from src.core.dependencies import get_gemini_client, get_replicate_client, get_storage_service
from src.services.gemini_client import GeminiClient
from src.services.replicate_client import ReplicateClient
from src.services.storage_service import StorageService


@pytest.fixture
def mock_replicate_client():
    mock = AsyncMock(spec=ReplicateClient)
    mock.generate_image.return_value = "https://replicate.delivery/output.jpg"
    mock.generate_image_via_image.return_value = "https://replicate.delivery/output.jpg"
    return mock

@pytest.fixture
def mock_storage_service():
    mock = AsyncMock(spec=StorageService)
    mock.save_file.return_value = ("user/generated_image.jpg", "image/jpeg", 100)
    mock.extract_key_from_url.return_value = "user/generated_image.jpg"
    mock.generate_presigned_url.return_value = "https://s3.url/signed"
    mock.get_presigned_urls_for_messages.return_value = {"user/generated_image.jpg": "https://s3.url/signed"}
    mock.generate_presigned_urls_batch.return_value = {"user/generated_image.jpg": "https://s3.url/signed"}
    return mock

@pytest.fixture
def mock_gemini_client():
    mock = AsyncMock(spec=GeminiClient)
    ai_response = MagicMock()
    ai_response.text = "Generated prompt from context"
    ai_response.token_count = 10
    mock.generate_response.return_value = ai_response
    return mock

@pytest.fixture
def override_dependencies(client, mock_replicate_client, mock_storage_service, mock_gemini_client):
    app = client.app
    app.dependency_overrides[get_replicate_client] = lambda: mock_replicate_client
    app.dependency_overrides[get_storage_service] = lambda: mock_storage_service
    app.dependency_overrides[get_gemini_client] = lambda: mock_gemini_client
    yield
    app.dependency_overrides = {}

@pytest.mark.asyncio
async def test_generate_image_endpoint(
    client,
    auth_headers,
    override_dependencies,
    mock_gemini_client,
    mock_replicate_client,
    mock_storage_service,
    clean_conversation_id
):
    conversation_id = clean_conversation_id
    
    mock_httpx_client = AsyncMock()
    mock_httpx_client.get.return_value = Response(200, content=b"fake_image_bytes")
    mock_httpx_client.__aenter__.return_value = mock_httpx_client
    mock_httpx_client.__aexit__.return_value = None
    
    with pytest.MonkeyPatch.context() as m:
        m.setattr("httpx.AsyncClient", lambda: mock_httpx_client)

        # 1. Test Generate with Explicit Prompt
        prompt = "A futuristic city"
        response = client.post(
            f"/api/v1/chat/conversations/{conversation_id}/images",
            headers=auth_headers,
            json={"prompt": prompt}
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["message_type"] == "image"
        assert "media_urls" in data
        assert len(data["media_urls"]) > 0
        
        mock_replicate_client.generate_image_via_image.assert_called()

        # 2. Test Generate WITHOUT Prompt (Context based)
        response = client.post(
            f"/api/v1/chat/conversations/{conversation_id}/images",
            headers=auth_headers,
            json={}
        )
        
        assert response.status_code == 201
        assert mock_gemini_client.generate_response.called
