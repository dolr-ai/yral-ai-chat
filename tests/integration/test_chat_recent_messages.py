"""
Additional tests for recent_messages in conversation list
"""

from datetime import datetime


def test_list_conversations_includes_recent_messages(client, clean_conversation_id, auth_headers):
    """Ensure list_conversations includes last messages as recent_messages"""
    # Send a few messages to ensure the conversation has history
    for i in range(3):
        response = client.post(
            f"/api/v1/chat/conversations/{clean_conversation_id}/messages",
            json={
                "content": f"Recent message {i}",
                "message_type": "text",
            },
            headers=auth_headers,
        )
        assert response.status_code == 200

    # Now list conversations
    response = client.get("/api/v1/chat/conversations", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()

    # Find our conversation
    convs = data["conversations"]
    target = next((c for c in convs if c["id"] == clean_conversation_id), None)
    assert target is not None

    # recent_messages should be present and contain at least the 3 new messages (up to 10 total)
    recent_messages = target.get("recent_messages")
    assert recent_messages is not None
    assert isinstance(recent_messages, list)
    assert 1 <= len(recent_messages) <= 10

    # Verify structure of a recent message
    msg = recent_messages[0]
    assert "id" in msg
    assert "role" in msg
    assert "content" in msg
    assert "message_type" in msg
    assert "media_urls" in msg
    assert "audio_url" in msg
    assert "audio_duration_seconds" in msg
    assert "token_count" in msg
    assert "created_at" in msg

    # Verify newest-first ordering if multiple messages present
    if len(recent_messages) > 1:
        t1 = datetime.fromisoformat(recent_messages[0]["created_at"])
        t2 = datetime.fromisoformat(recent_messages[1]["created_at"])
        assert t1 >= t2
