from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_send_message_triggers_all_notifications(client, clean_conversation_id, auth_headers):
    """
    Verify that sending a message:
    1. Broadcasts typing status (start and end)
    2. Broadcasts new message via WebSocket
    3. Sends a push notification
    """
    with patch("src.services.chat_service.manager") as mock_manager, \
         patch("src.services.chat_service.notification_service") as mock_notification_service:
        
        # Configure mocks
        mock_manager.emit_typing_status_event = AsyncMock()
        mock_manager.emit_new_message_event = AsyncMock()
        mock_notification_service.send_push_notification = AsyncMock(return_value=True)
        
        # Send message
        response = client.post(
            f"/api/v1/chat/conversations/{clean_conversation_id}/messages",
            json={"content": "Hello", "message_type": "text"},
            headers=auth_headers
        )
        
        assert response.status_code == 200
        
        # 1. Verify typing status broadcasts
        # Called at least twice: start (True) and end (False)
        typing_calls = mock_manager.emit_typing_status_event.call_args_list
        assert len(typing_calls) >= 2
        assert typing_calls[0].kwargs["is_typing"] is True
        assert typing_calls[-1].kwargs["is_typing"] is False
        
        # 2. Verify new message broadcast
        mock_manager.emit_new_message_event.assert_called_once()
        new_msg_args = mock_manager.emit_new_message_event.call_args
        assert str(new_msg_args.kwargs["conversation_id"]) == clean_conversation_id
        assert hasattr(new_msg_args.kwargs["message"], "content")
        assert "unread_count" in new_msg_args.kwargs
        
        # 3. Verify push notification
        mock_notification_service.send_push_notification.assert_called_once()
        pn_args = mock_notification_service.send_push_notification.call_args
        assert pn_args.kwargs["title"] is not None
        assert hasattr(pn_args.kwargs["data"], "conversation_id")
        assert pn_args.kwargs["data"].conversation_id == clean_conversation_id

@pytest.mark.asyncio
async def test_mark_as_read_triggers_websocket_broadcast(client, clean_conversation_id, auth_headers):
    """Verify that marking as read broadcasts a WebSocket event"""
    with patch("src.services.chat_service.manager") as mock_manager:
        mock_manager.emit_conversation_read_event = AsyncMock()
        
        response = client.post(
            f"/api/v1/chat/conversations/{clean_conversation_id}/read",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        mock_manager.emit_conversation_read_event.assert_called_once()
        args = mock_manager.emit_conversation_read_event.call_args
        assert str(args.kwargs["conversation_id"]) == clean_conversation_id
        assert "read_at" in args.kwargs
