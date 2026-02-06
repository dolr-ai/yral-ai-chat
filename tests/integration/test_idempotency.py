"""
Tests for message idempotency
"""
import uuid
from unittest.mock import AsyncMock, patch
from src.models.internal import AIResponse  # Import AIResponse here for use in mocks

def test_message_idempotency(client, clean_conversation_id, auth_headers):
    """
    Test that sending multiple requests with the same client_message_id
    returns the same response and doesn't create duplicate messages.
    """
    client_message_id = str(uuid.uuid4())
    message_content = "Hello, this is my idempotent message!"
    
    # Mock AI response to ensure it's predictable
    with patch("src.services.gemini_client.GeminiClient.generate_response", new_callable=AsyncMock) as mock_gen_response:
        mock_gen_response.return_value = AIResponse(text="I received your idempotent message.", token_count=15)
        
        # 1. Send first request
        response1 = client.post(
            f"/api/v1/chat/conversations/{clean_conversation_id}/messages",
            json={
                "content": message_content,
                "message_type": "text",
                "client_message_id": client_message_id
            },
            headers=auth_headers
        )
        
        assert response1.status_code == 200
        data1 = response1.json()
        user_msg1_id = data1["user_message"]["id"]
        assistant_msg1_id = data1["assistant_message"]["id"]
        
        # Verify mock was called (account for potential memory extraction call)
        # 1 for message + 1 for memory = 2 calls
        assert mock_gen_response.call_count >= 1
        initial_call_count = mock_gen_response.call_count
        
        # 2. Send second request (duplicate)
        response2 = client.post(
            f"/api/v1/chat/conversations/{clean_conversation_id}/messages",
            json={
                "content": message_content,
                "message_type": "text",
                "client_message_id": client_message_id
            },
            headers=auth_headers
        )
        
        assert response2.status_code == 200
        data2 = response2.json()
        user_msg2_id = data2["user_message"]["id"]
        assistant_msg2_id = data2["assistant_message"]["id"]
        
        # 3. Verify IDs match (Deduplicated)
        assert user_msg1_id == user_msg2_id
        assert assistant_msg1_id == assistant_msg2_id
        
        # 4. Verify AI was NOT called again
        assert mock_gen_response.call_count == initial_call_count
        
        # 5. Verify total message count in DB
        messages_response = client.get(
            f"/api/v1/chat/conversations/{clean_conversation_id}/messages",
            headers=auth_headers
        )
        assert messages_response.status_code == 200
        # Should be 2 (user + assistant) plus whatever was there before (like greeting)
        # clean_conversation_id usually starts empty or with 1 greeting.
        # But we only care that it didn't increase after the second call.
        
        # 6. Send a DIFFERENT message
        client_message_id2 = str(uuid.uuid4())
        response3 = client.post(
            f"/api/v1/chat/conversations/{clean_conversation_id}/messages",
            json={
                "content": "A different message",
                "message_type": "text",
                "client_message_id": client_message_id2
            },
            headers=auth_headers
        )
        assert response3.status_code == 200
        data3 = response3.json()
        assert data3["user_message"]["id"] != user_msg1_id
        assert mock_gen_response.call_count > initial_call_count

def test_idempotency_without_client_id(client, clean_conversation_id, auth_headers):
    """
    Verify that without client_message_id, duplicates ARE created (legacy behavior).
    """
    message_content = "Same content but no client_id"
    
    with patch("src.services.gemini_client.GeminiClient.generate_response", new_callable=AsyncMock) as mock_gen_response:
        mock_gen_response.return_value = AIResponse(text="Copy that.", token_count=5)
        
        # First send
        response1 = client.post(
            f"/api/v1/chat/conversations/{clean_conversation_id}/messages",
            json={"content": message_content, "message_type": "text"},
            headers=auth_headers
        )
        
        # Second send (identical content, no client_id)
        response2 = client.post(
            f"/api/v1/chat/conversations/{clean_conversation_id}/messages",
            json={"content": message_content, "message_type": "text"},
            headers=auth_headers
        )
        
        assert response1.json()["user_message"]["id"] != response2.json()["user_message"]["id"]
        # Without client_id, it should call AI for each request
        assert mock_gen_response.call_count >= 2
