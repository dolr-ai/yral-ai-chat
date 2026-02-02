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

    # Find our conversation (response is now a direct list)
    target = next((c for c in data if c["id"] == clean_conversation_id), None)
    assert target is not None

    # last_message should be present (replaces recent_messages)
    last_message = target.get("last_message")
    assert last_message is not None
    assert isinstance(last_message, dict)

    # Verify structure of the last message
    assert "content" in last_message
    assert "role" in last_message
    assert "created_at" in last_message
    assert "status" in last_message
    assert "is_read" in last_message
