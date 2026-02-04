from unittest.mock import MagicMock, patch

import pytest

from src.services.notification_service import (
    MetadataPNProvider,
    NotificationService,
)


@pytest.mark.asyncio
async def test_metadata_pn_provider_send_success():
    provider = MetadataPNProvider()
    user_id = "test_user"
    title = "Hello"
    body = "World"
    
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        result = await provider.send_notification(user_id, title, body)
        
        assert result is True
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert user_id in args[0]
        assert kwargs["json"]["data"]["title"] == title


@pytest.mark.asyncio
async def test_metadata_pn_provider_send_failure():
    provider = MetadataPNProvider()
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=500, text="Error")
        result = await provider.send_notification("user", "T", "B")
        assert result is False


@pytest.mark.asyncio
async def test_notification_service_integration():
    mock_provider = MagicMock(spec=MetadataPNProvider)
    mock_provider.send_notification = pytest.importorskip("unittest.mock").AsyncMock(return_value=True)
    
    service = NotificationService(provider=mock_provider)
    success = await service.send_push_notification("user1", "T", "B")
    
    assert success is True
    mock_provider.send_notification.assert_called_once_with("user1", "T", "B", None)
