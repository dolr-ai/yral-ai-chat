"""
Tests for chat endpoints
"""
from datetime import datetime
from uuid import UUID


def test_create_conversation(client, test_influencer_id, auth_headers):
    """Test creating a new conversation"""
    response = client.post(
        "/api/v1/chat/conversations",
        json={"influencer_id": test_influencer_id},
        headers=auth_headers
    )

    assert response.status_code == 201
    data = response.json()

    # Verify response structure
    assert "id" in data
    assert "user_id" in data
    assert "influencer" in data
    assert "created_at" in data
    assert "updated_at" in data
    assert "message_count" in data

    # Verify data types
    UUID(data["id"])
    assert isinstance(data["user_id"], str)
    assert isinstance(data["message_count"], int)

    # Verify influencer info
    influencer = data["influencer"]
    assert "id" in influencer
    assert influencer["id"] == test_influencer_id
    assert "name" in influencer
    assert "display_name" in influencer
    assert "avatar_url" in influencer
    assert "suggested_messages" in influencer
    assert isinstance(influencer["suggested_messages"], list)


def test_create_conversation_with_initial_greeting_sets_message_count_and_greeting(client, auth_headers):
    """New conversation with an influencer that has initial_greeting should:
    - create a greeting message
    - return message_count == 1
    - include greeting_message in the response
    """
    # Use Ahaan Sharma's influencer ID (known to have initial_greeting)
    influencer_id = "qg2pi-g3xl4-uprdd-macwr-64q7r-plotv-xm3bg-iayu3-rnpux-7ikkz-hqe"

    # Create a new conversation for that influencer
    response = client.post(
        "/api/v1/chat/conversations",
        json={"influencer_id": influencer_id},
        headers=auth_headers
    )

    assert response.status_code == 201
    data = response.json()

    # 3) message_count should reflect the greeting message that was auto-created
    assert "message_count" in data
    assert data["message_count"] == 1

    # 4) greeting_message should be present and structured correctly
    greeting = data.get("greeting_message")
    assert greeting is not None
    assert greeting.get("role") == "assistant"
    assert isinstance(greeting.get("content"), str)
    assert greeting["content"].strip() != ""

    # 5) created_at of greeting should be a valid ISO timestamp
    assert "created_at" in greeting
    datetime.fromisoformat(greeting["created_at"])


def test_initial_greeting_message_appears_in_conversation_history(client, auth_headers):
    """Verify that the initial greeting message is viewable in conversation message history"""
    # Use Ahaan Sharma's influencer ID (known to have initial_greeting)
    influencer_id = "qg2pi-g3xl4-uprdd-macwr-64q7r-plotv-xm3bg-iayu3-rnpux-7ikkz-hqe"

    # 1) Create a new conversation for that influencer
    create_response = client.post(
        "/api/v1/chat/conversations",
        json={"influencer_id": influencer_id},
        headers=auth_headers
    )
    assert create_response.status_code == 201
    conversation_data = create_response.json()
    conversation_id = conversation_data["id"]

    # Verify greeting was returned in create response
    greeting_from_create = conversation_data.get("greeting_message")
    assert greeting_from_create is not None
    expected_greeting_content = greeting_from_create["content"]

    # 2) Fetch conversation messages to verify greeting is in history
    messages_response = client.get(
        f"/api/v1/chat/conversations/{conversation_id}/messages",
        params={"limit": 50, "order": "asc"},  # asc to get oldest first (greeting should be first)
        headers=auth_headers
    )
    assert messages_response.status_code == 200
    messages_data = messages_response.json()

    # 3) Verify messages list structure
    assert "messages" in messages_data
    assert "total" in messages_data
    assert messages_data["total"] == 1  # Should only have the greeting message

    # 4) Verify greeting message is in the list
    messages = messages_data["messages"]
    assert len(messages) == 1

    greeting_message = messages[0]

    # 5) Verify greeting message structure and content
    assert greeting_message["role"] == "assistant"
    assert greeting_message["content"] == expected_greeting_content
    assert greeting_message["content"].strip() != ""
    assert greeting_message["message_type"] == "text"
    assert "id" in greeting_message
    assert "created_at" in greeting_message
    datetime.fromisoformat(greeting_message["created_at"])

    # 6) Verify it matches the greeting from create response
    assert greeting_message["content"] == greeting_from_create["content"]
    assert greeting_message["role"] == greeting_from_create["role"]


def test_create_conversation_returns_existing(client, test_influencer_id, auth_headers):
    """Test creating a conversation returns existing one if it exists"""
    # Create first conversation
    response1 = client.post(
        "/api/v1/chat/conversations",
        json={"influencer_id": test_influencer_id},
        headers=auth_headers
    )
    assert response1.status_code == 201
    conv1_id = response1.json()["id"]

    # Try to create another with same influencer
    response2 = client.post(
        "/api/v1/chat/conversations",
        json={"influencer_id": test_influencer_id},
        headers=auth_headers
    )
    assert response2.status_code == 201
    conv2_id = response2.json()["id"]

    # Should return the same conversation
    assert conv1_id == conv2_id


def test_list_conversations(client, test_conversation_id, auth_headers):
    """Test listing user's conversations"""
    response = client.get("/api/v1/chat/conversations", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert "conversations" in data
    assert "total" in data
    assert "limit" in data
    assert "offset" in data

    # Verify pagination defaults
    assert data["limit"] == 20
    assert data["offset"] == 0

    # Verify we have conversations
    assert isinstance(data["conversations"], list)
    assert data["total"] > 0


def test_list_conversations_with_pagination(client, auth_headers):
    """Test listing conversations with custom pagination"""
    response = client.get("/api/v1/chat/conversations?limit=5&offset=0", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()

    assert data["limit"] == 5
    assert data["offset"] == 0
    assert len(data["conversations"]) <= 5


def test_list_conversations_filtered_by_influencer(client, test_influencer_id, auth_headers):
    """Test listing conversations filtered by influencer_id"""
    response = client.get(
        f"/api/v1/chat/conversations?influencer_id={test_influencer_id}",
        headers=auth_headers
    )

    assert response.status_code == 200
    data = response.json()

    # All conversations should be with the specified influencer
    for conv in data["conversations"]:
        assert conv["influencer"]["id"] == test_influencer_id


def test_list_conversations_response_structure(client, test_conversation_id, auth_headers):
    """Test conversation response contains all required fields"""
    response = client.get("/api/v1/chat/conversations", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert len(data["conversations"]) > 0

    conv = data["conversations"][0]

    # Verify required fields
    assert "id" in conv
    assert "user_id" in conv
    assert "influencer" in conv
    assert "created_at" in conv
    assert "updated_at" in conv
    assert "message_count" in conv

    # Verify data types
    UUID(conv["id"])
    assert isinstance(conv["user_id"], str)
    assert isinstance(conv["message_count"], int)

    # recent_messages is optional but, if present, must be a list
    if "recent_messages" in conv and conv["recent_messages"] is not None:
        assert isinstance(conv["recent_messages"], list)

    # Verify timestamps
    datetime.fromisoformat(conv["created_at"])
    datetime.fromisoformat(conv["updated_at"])


def test_list_messages(client, test_conversation_id, auth_headers):
    """Test listing messages in a conversation"""
    response = client.get(
        f"/api/v1/chat/conversations/{test_conversation_id}/messages",
        headers=auth_headers
    )

    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert "conversation_id" in data
    assert "messages" in data
    assert "total" in data
    assert "limit" in data
    assert "offset" in data

    assert data["conversation_id"] == test_conversation_id
    assert data["limit"] == 50
    assert data["offset"] == 0


def test_list_messages_with_pagination(client, test_conversation_id, auth_headers):
    """Test listing messages with custom pagination"""
    response = client.get(
        f"/api/v1/chat/conversations/{test_conversation_id}/messages?limit=10&offset=0",
        headers=auth_headers
    )

    assert response.status_code == 200
    data = response.json()

    assert data["limit"] == 10
    assert data["offset"] == 0
    assert len(data["messages"]) <= 10


def test_list_messages_ordering_desc(client, test_conversation_id, auth_headers):
    """Test listing messages with descending order (newest first)"""
    response = client.get(
        f"/api/v1/chat/conversations/{test_conversation_id}/messages?order=desc&limit=10",
        headers=auth_headers
    )

    assert response.status_code == 200
    data = response.json()

    # Verify messages are in descending order if there are multiple
    if len(data["messages"]) > 1:
        msg1_time = datetime.fromisoformat(data["messages"][0]["created_at"])
        msg2_time = datetime.fromisoformat(data["messages"][1]["created_at"])
        assert msg1_time >= msg2_time


def test_list_messages_ordering_asc(client, test_conversation_id, auth_headers):
    """Test listing messages with ascending order (oldest first)"""
    response = client.get(
        f"/api/v1/chat/conversations/{test_conversation_id}/messages?order=asc&limit=10",
        headers=auth_headers
    )

    assert response.status_code == 200
    data = response.json()

    # Verify messages are in ascending order if there are multiple
    if len(data["messages"]) > 1:
        msg1_time = datetime.fromisoformat(data["messages"][0]["created_at"])
        msg2_time = datetime.fromisoformat(data["messages"][1]["created_at"])
        assert msg1_time <= msg2_time


def test_send_text_message(client, clean_conversation_id, auth_headers):
    """Test sending a text message"""
    response = client.post(
        f"/api/v1/chat/conversations/{clean_conversation_id}/messages",
        json={
            "content": "Hello, this is a test message!",
            "message_type": "text"
        },
        headers=auth_headers
    )

    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert "user_message" in data
    assert "assistant_message" in data

    # Verify user message
    user_msg = data["user_message"]
    assert user_msg["role"] == "user"
    assert user_msg["content"] == "Hello, this is a test message!"
    assert user_msg["message_type"] == "text"
    assert "id" in user_msg
    assert "created_at" in user_msg

    # Verify assistant message
    assistant_msg = data["assistant_message"]
    assert assistant_msg["role"] == "assistant"
    assert assistant_msg["message_type"] == "text"
    assert len(assistant_msg["content"]) > 0
    assert "id" in assistant_msg
    assert "created_at" in assistant_msg


def test_send_message_validation_error_missing_content(client, test_conversation_id, auth_headers):
    """Test sending message with missing content for text type"""
    response = client.post(
        f"/api/v1/chat/conversations/{test_conversation_id}/messages",
        json={
            "content": "",
            "message_type": "text"
        },
        headers=auth_headers
    )

    # Should return 422 validation error
    assert response.status_code == 422
    data = response.json()
    assert "error" in data
    assert data["error"] == "validation_error"
    assert "message" in data


def test_send_message_validation_error_invalid_type(client, test_conversation_id, auth_headers):
    """Test sending message with invalid message type"""
    response = client.post(
        f"/api/v1/chat/conversations/{test_conversation_id}/messages",
        json={
            "content": "Test",
            "message_type": "invalid_type"
        },
        headers=auth_headers
    )

    # Should return 422 validation error
    assert response.status_code == 422
    data = response.json()
    assert "error" in data
    assert data["error"] == "validation_error"
    assert "message" in data


def test_send_message_to_invalid_conversation(client, auth_headers):
    """Test sending message to non-existent conversation"""
    fake_uuid = "00000000-0000-0000-0000-000000000000"
    response = client.post(
        f"/api/v1/chat/conversations/{fake_uuid}/messages",
        json={
            "content": "Test message",
            "message_type": "text"
        },
        headers=auth_headers
    )

    # Should return 404 not found
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert data["error"] == "not_found"
    assert "message" in data


def test_send_message_response_structure(client, clean_conversation_id, auth_headers):
    """Test message response contains all required fields"""
    response = client.post(
        f"/api/v1/chat/conversations/{clean_conversation_id}/messages",
        json={
            "content": "Test message structure",
            "message_type": "text"
        },
        headers=auth_headers
    )

    assert response.status_code == 200
    data = response.json()

    user_msg = data["user_message"]

    # Verify all required fields
    assert "id" in user_msg
    assert "role" in user_msg
    assert "content" in user_msg
    assert "message_type" in user_msg
    assert "media_urls" in user_msg
    assert "audio_url" in user_msg
    assert "audio_duration_seconds" in user_msg
    assert "token_count" in user_msg
    assert "created_at" in user_msg

    # Verify data types
    UUID(user_msg["id"])
    assert isinstance(user_msg["media_urls"], list)
    datetime.fromisoformat(user_msg["created_at"])


def test_delete_conversation(client, clean_conversation_id, auth_headers):
    """Test deleting a conversation"""
    response = client.delete(
        f"/api/v1/chat/conversations/{clean_conversation_id}",
        headers=auth_headers
    )

    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert "success" in data
    assert "message" in data
    assert "deleted_conversation_id" in data
    assert "deleted_messages_count" in data

    assert data["success"] is True
    assert data["deleted_conversation_id"] == clean_conversation_id
    assert isinstance(data["deleted_messages_count"], int)


def test_delete_nonexistent_conversation(client, auth_headers):
    """Test deleting a conversation that doesn't exist"""
    fake_uuid = "00000000-0000-0000-0000-000000000000"
    response = client.delete(
        f"/api/v1/chat/conversations/{fake_uuid}",
        headers=auth_headers
    )

    # Should return 404 not found
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert data["error"] == "not_found"
    assert "message" in data

def test_message_content_not_duplicated(client, clean_conversation_id, auth_headers):
    """
    Test that message content is not duplicated or modified by the backend.
    Specifically tests the "80" -> "8080" issue to ensure backend passes content through correctly.
    """
    # Send a message with content "80" (the problematic case)
    test_content = "80"
    
    response = client.post(
        f"/api/v1/chat/conversations/{clean_conversation_id}/messages",
        json={
            "content": test_content,
            "message_type": "text"
        },
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify user message in response matches exactly what was sent
    user_msg = data["user_message"]
    assert user_msg["role"] == "user"
    assert user_msg["content"] == test_content, \
        f"Expected content '{test_content}' but got '{user_msg['content']}'. " \
        f"Content was duplicated or modified by backend!"
    assert user_msg["message_type"] == "text"
    assert "id" in user_msg
    
    # Verify the message was stored correctly by fetching it back
    message_id = user_msg["id"]
    messages_response = client.get(
        f"/api/v1/chat/conversations/{clean_conversation_id}/messages",
        params={"limit": 10, "order": "desc"},
        headers=auth_headers
    )
    
    assert messages_response.status_code == 200
    messages_data = messages_response.json()
    
    # Find the message we just sent
    found_message = None
    for msg in messages_data["messages"]:
        if msg["id"] == message_id:
            found_message = msg
            break
    
    assert found_message is not None, "Message not found in conversation history"
    assert found_message["content"] == test_content, \
        f"Message content in database is '{found_message['content']}' but expected '{test_content}'. " \
        f"Content was modified during storage or retrieval!"
    
    # Additional check: verify content doesn't contain "8080"
    assert "8080" not in user_msg["content"], \
        f"Content was incorrectly duplicated to '{user_msg['content']}'"
    assert "8080" not in found_message["content"], \
        f"Stored message content was incorrectly duplicated to '{found_message['content']}'"


def test_short_numeric_message_preserved(client, clean_conversation_id, auth_headers):
    """
    Test that short numeric messages (like "80") are preserved exactly as sent.
    This is a regression test for the "8080" duplication issue.
    """
    test_cases = [
        "80",
        "80 kilos",
        "80kg",
        "80.5",
        "80.0",
    ]
    
    for test_content in test_cases:
        response = client.post(
            f"/api/v1/chat/conversations/{clean_conversation_id}/messages",
            json={
                "content": test_content,
                "message_type": "text"
            },
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        user_msg = data["user_message"]
        assert user_msg["content"] == test_content, \
            f"Content '{test_content}' was modified to '{user_msg['content']}'"
        
        # Get the user message ID from the response
        user_message_id = user_msg["id"]
        
        # Verify it's stored correctly by fetching messages and finding the user message
        messages_response = client.get(
            f"/api/v1/chat/conversations/{clean_conversation_id}/messages",
            params={"limit": 10, "order": "desc"},
            headers=auth_headers
        )
        
        assert messages_response.status_code == 200
        messages = messages_response.json()["messages"]
        
        # Find the user message by ID
        stored_user_msg = None
        for msg in messages:
            if msg["id"] == user_message_id:
                stored_user_msg = msg
                break
        
        assert stored_user_msg is not None, f"User message {user_message_id} not found in conversation history"
        assert stored_user_msg["content"] == test_content, \
            f"Stored content '{stored_user_msg['content']}' doesn't match sent content '{test_content}'"
        assert stored_user_msg["role"] == "user", "Found message is not a user message"