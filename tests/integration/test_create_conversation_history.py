"""
Integration tests for create_conversation history reload
"""

def test_create_conversation_history_reload_v1(client, test_influencer_id, auth_headers):
    """Verify that V1 create_conversation returns history for existing conversations"""
    # 1. Create a conversation
    create_response = client.post(
        "/api/v1/chat/conversations",
        json={"influencer_id": test_influencer_id},
        headers=auth_headers
    )
    assert create_response.status_code == 201
    conversation_id = create_response.json()["id"]
    
    # 2. Send 3 messages
    for i in range(3):
        send_response = client.post(
            f"/api/v1/chat/conversations/{conversation_id}/messages",
            json={"content": f"Test message {i}", "message_type": "text"},
            headers=auth_headers
        )
        assert send_response.status_code == 200
        
    # 3. Call create_conversation again (should return existing)
    reopen_response = client.post(
        "/api/v1/chat/conversations",
        json={"influencer_id": test_influencer_id},
        headers=auth_headers
    )
    assert reopen_response.status_code == 201
    data = reopen_response.json()
    
    assert data["id"] == conversation_id
    # Should have greeting + 3 user messages + 3 assistant responses = 7 total
    assert data["message_count"] >= 7
    assert "recent_messages" in data
    assert len(data["recent_messages"]) > 0
    # recent_messages are newest first by default in V1
    assert data["recent_messages"][0]["role"] == "assistant"

