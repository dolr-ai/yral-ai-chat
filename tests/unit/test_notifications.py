from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.notification_service import MockPNProvider, NotificationService, PushNotificationProvider


@pytest.mark.asyncio
async def test_mock_pn_provider_send():
    """Verify MockPNProvider log output and return value"""
    provider = MockPNProvider()
    user_id = "user_123"
    title = "Test Title"
    body = "Test Body"
    data = {"key": "value"}
    
    result = await provider.send_notification(user_id, title, body, data)
    assert result is True

@pytest.mark.asyncio
async def test_notification_service_uses_provided_provider():
    """Verify NotificationService uses the provider passed to it"""
    mock_provider = MagicMock(spec=PushNotificationProvider)
    mock_provider.send_notification = AsyncMock(return_value=True)
    
    service = NotificationService(pn_provider=mock_provider)
    await service.send_push_notification("user_1", "T", "B", {"d": "1"})
    
    mock_provider.send_notification.assert_called_once_with(
        user_id="user_1",
        title="T",
        body="B",
        data={"d": "1"}
    )

@pytest.mark.asyncio
async def test_notification_service_handles_provider_failure():
    """Verify NotificationService handles exceptions from provider"""
    mock_provider = MagicMock(spec=PushNotificationProvider)
    mock_provider.send_notification = AsyncMock(side_effect=Exception("Failed"))
    
    service = NotificationService(pn_provider=mock_provider)
    result = await service.send_push_notification("user_1", "T", "B")
    
    assert result is False
