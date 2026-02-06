"""
Additional tests for recent_messages in conversation list
"""


def test_list_conversations_includes_recent_messages(client, clean_conversation_id, auth_headers):
    """Ensure list_conversations includes last_message"""
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

    # Find our conversation (response is paginated object)
    conversations = data["conversations"]
    target = next((c for c in conversations if c["id"] == clean_conversation_id), None)
    assert target is not None

    # recent_messages should be present (V1 behavior)
    recent_messages = target.get("recent_messages")
    assert recent_messages is not None
    assert isinstance(recent_messages, list)
    assert len(recent_messages) > 0

    # Verify structure of a recent message
    msg = recent_messages[0]
    assert "content" in msg
    assert "role" in msg
    assert "created_at" in msg
    assert "status" in msg
    assert "is_read" in msg
