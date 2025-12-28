#!/usr/bin/env python3
"""
Test script to create a new test user, authenticate, create a conversation,
and check if the greeting message is returned.

Usage:
    python3 scripts/test_conversation_greeting.py
    python3 scripts/test_conversation_greeting.py --influencer-id <id>
    python3 scripts/test_conversation_greeting.py --base-url https://chat.yral.com/staging
    python3 scripts/test_conversation_greeting.py --base-url http://localhost:8000  # For local testing
"""
import argparse
import base64
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import requests


def encode_jwt(payload: dict) -> str:
    """Create a dummy JWT token for testing."""
    header = {
        "typ": "JWT",
        "alg": "ES256",
        "kid": "default",
    }

    def b64url(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

    header_b64 = b64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))

    signature_b64 = "dummy_signature"

    return f"{header_b64}.{payload_b64}.{signature_b64}"


def generate_test_token(user_id: str = None, expires_in_seconds: int = 3600) -> str:
    """
    Generate a test JWT token for testing

    Args:
        user_id: User ID to include in token (mapped to `sub`). If None, generates random ID.
        expires_in_seconds: Token expiration time in seconds

    Returns:
        JWT token string
    """
    if user_id is None:
        user_id = f"test_user_{int(time.time())}"

    now = int(time.time())

    payload = {
        "sub": user_id,
        "iss": "https://auth.yral.com",
        "iat": now,
        "exp": now + expires_in_seconds,
    }

    return encode_jwt(payload)


def get_active_influencer(base_url: str) -> str:
    """Get the first active influencer ID from the API."""
    try:
        response = requests.get(f"{base_url}/api/v1/influencers?limit=1")
        response.raise_for_status()
        data = response.json()
        if data.get("total", 0) > 0:
            return data["influencers"][0]["id"]
        else:
            raise ValueError("No active influencers found")
    except Exception as e:
        raise RuntimeError(f"Failed to get influencer: {e}") from e


def create_conversation(base_url: str, token: str, influencer_id: str) -> dict:
    """Create a new conversation and return the response."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    payload = {"influencer_id": influencer_id}

    try:
        response = requests.post(
            f"{base_url}/api/v1/chat/conversations",
            json=payload,
            headers=headers,
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        error_detail = ""
        try:
            error_detail = response.json()
        except:
            error_detail = response.text
        raise RuntimeError(f"HTTP {response.status_code}: {error_detail}") from e
    except Exception as e:
        raise RuntimeError(f"Failed to create conversation: {e}") from e


def delete_conversation(base_url: str, token: str, conversation_id: str) -> dict:
    """Delete a conversation and return the response."""
    headers = {
        "Authorization": f"Bearer {token}",
    }

    try:
        response = requests.delete(
            f"{base_url}/api/v1/chat/conversations/{conversation_id}",
            headers=headers,
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        error_detail = ""
        try:
            error_detail = response.json()
        except:
            error_detail = response.text
        raise RuntimeError(f"HTTP {response.status_code}: {error_detail}") from e
    except Exception as e:
        raise RuntimeError(f"Failed to delete conversation: {e}") from e


def get_conversations(base_url: str, token: str, influencer_id: str = None) -> dict:
    """Get list of conversations and return the response."""
    headers = {
        "Authorization": f"Bearer {token}",
    }

    params = {}
    if influencer_id:
        params["influencer_id"] = influencer_id

    try:
        response = requests.get(
            f"{base_url}/api/v1/chat/conversations",
            headers=headers,
            params=params,
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        error_detail = ""
        try:
            error_detail = response.json()
        except:
            error_detail = response.text
        raise RuntimeError(f"HTTP {response.status_code}: {error_detail}") from e
    except Exception as e:
        raise RuntimeError(f"Failed to get conversations: {e}") from e


def get_conversation_messages(base_url: str, token: str, conversation_id: str) -> dict:
    """Get messages for a conversation and return the response."""
    headers = {
        "Authorization": f"Bearer {token}",
    }

    try:
        response = requests.get(
            f"{base_url}/api/v1/chat/conversations/{conversation_id}/messages",
            headers=headers,
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        error_detail = ""
        try:
            error_detail = response.json()
        except:
            error_detail = response.text
        raise RuntimeError(f"HTTP {response.status_code}: {error_detail}") from e
    except Exception as e:
        raise RuntimeError(f"Failed to get conversation messages: {e}") from e


def main():
    parser = argparse.ArgumentParser(
        description="Test conversation creation with greeting message"
    )
    parser.add_argument(
        "--base-url",
        default="https://chat.yral.com/staging",
        help="Base URL of the API (default: https://chat.yral.com/staging)",
    )
    parser.add_argument(
        "--influencer-id",
        help="Influencer ID to use (default: first active influencer)",
    )
    parser.add_argument(
        "--user-id",
        help="User ID for the test user (default: auto-generated)",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("Test: Create Conversation and Check for Greeting Message")
    print("=" * 70)
    print()

    # Step 1: Generate test user and token
    print("📝 Step 1: Generating test user and JWT token...")
    user_id = args.user_id or f"test_user_{int(time.time())}"
    token = generate_test_token(user_id=user_id)
    print(f"   ✅ User ID: {user_id}")
    print(f"   ✅ Token generated (expires in 1 hour)")
    print()

    # Step 2: Get influencer ID
    print("🔍 Step 2: Getting influencer ID...")
    if args.influencer_id:
        influencer_id = args.influencer_id
        print(f"   ✅ Using provided influencer ID: {influencer_id}")
    else:
        try:
            influencer_id = get_active_influencer(args.base_url)
            print(f"   ✅ Found influencer ID: {influencer_id}")
        except Exception as e:
            print(f"   ❌ Error: {e}")
            sys.exit(1)
    print()

    # Step 3: Create conversation
    print("💬 Step 3: Creating new conversation...")
    try:
        conversation_data = create_conversation(args.base_url, token, influencer_id)
        print("   ✅ Conversation created successfully!")
        print()
    except Exception as e:
        print(f"   ❌ Error creating conversation: {e}")
        sys.exit(1)

    # Step 4: Display results
    print("=" * 70)
    print("📊 Conversation Details")
    print("=" * 70)
    print(f"Conversation ID: {conversation_data.get('id')}")
    print(f"User ID: {conversation_data.get('user_id')}")
    print(f"Message Count: {conversation_data.get('message_count', 0)}")
    print(f"Created At: {conversation_data.get('created_at')}")
    print()

    # Influencer info
    influencer = conversation_data.get("influencer", {})
    print("👤 Influencer:")
    print(f"   ID: {influencer.get('id')}")
    print(f"   Name: {influencer.get('name')}")
    print(f"   Display Name: {influencer.get('display_name')}")
    print()

    # Check for greeting message
    print("=" * 70)
    print("🎉 Greeting Message Check")
    print("=" * 70)

    message_count = conversation_data.get("message_count", 0)
    greeting_message = conversation_data.get("greeting_message")
    recent_messages = conversation_data.get("recent_messages")

    if message_count > 1:
        print(f"ℹ️  This conversation already existed with {message_count} messages.")
        print("   For existing conversations with >1 message, the API returns")
        print("   'recent_messages' instead of 'greeting_message'.")
        print()
        if recent_messages:
            print(f"   📨 Found {len(recent_messages)} recent messages")
            # Check if the first message (newest) is the greeting
            first_msg = recent_messages[0] if recent_messages else None
            if first_msg and first_msg.get("role") == "assistant":
                print("   ✅ The oldest message (first in recent_messages) is from assistant")
                print("   💡 This is likely the initial greeting message")
        print()
        print("   💡 To test greeting message creation, use a unique user_id:")
        print(f"      python3 {Path(__file__).name} --user-id unique_user_{int(time.time())}")
    elif greeting_message:
        print("✅ SUCCESS: Greeting message IS returned!")
        print("   (This is a NEW conversation)")
        print()
        print("Greeting Message Details:")
        print(f"   Role: {greeting_message.get('role')}")
        print(f"   Created At: {greeting_message.get('created_at')}")
        print()
        print("Content:")
        print("-" * 70)
        content = greeting_message.get("content", "")
        # Wrap text nicely
        words = content.split()
        line = ""
        for word in words:
            if len(line + word) > 68:
                print(f"   {line}")
                line = word + " "
            else:
                line += word + " "
        if line.strip():
            print(f"   {line.strip()}")
        print("-" * 70)
    else:
        print("❌ WARNING: Greeting message is NOT returned in the response")
        print()
        print("Possible reasons:")
        print("   - Influencer does not have an initial_greeting configured")
        print("   - Error occurred during greeting creation")
        print("   - Conversation already existed but message_count is 0 or 1")

    print()

    # Show suggested messages if available
    suggested_messages = influencer.get("suggested_messages")
    if suggested_messages:
        print("💡 Suggested Messages:")
        for i, msg in enumerate(suggested_messages, 1):
            print(f"   {i}. {msg}")
        print()

    # Show full JSON response (optional, can be commented out)
    print("=" * 70)
    print("📄 Full JSON Response (formatted)")
    print("=" * 70)
    print(json.dumps(conversation_data, indent=2))
    print()

    # Summary
    print("=" * 70)
    print("✅ Test Complete")
    print("=" * 70)
    if message_count > 1:
        print("ℹ️  RESULT: Conversation already existed with multiple messages.")
        print("   The greeting message feature appears to be working (check recent_messages).")
        print("   For a clean test, use a unique user_id to create a new conversation.")
    elif greeting_message:
        print("🎉 RESULT: Greeting message feature is working correctly!")
    else:
        print("⚠️  RESULT: No greeting message found - check the reasons above")
    print()

    # New Test: Delete and recreate, then test all 3 endpoints
    print("=" * 70)
    print("🧪 Test: Delete Conversation and Verify Greeting in All 3 Endpoints")
    print("=" * 70)
    print()

    conversation_id = conversation_data.get("id")
    if not conversation_id:
        print("⚠️  Skipping delete/recreate test: No conversation ID found")
        return

    # Step 1: Delete the conversation
    print("🗑️  Step 1: Deleting conversation...")
    try:
        delete_result = delete_conversation(args.base_url, token, conversation_id)
        deleted_count = delete_result.get("deleted_messages_count", 0)
        print(f"   ✅ Conversation deleted successfully!")
        print(f"   ✅ Deleted {deleted_count} message(s)")
        print()
    except Exception as e:
        print(f"   ❌ Error deleting conversation: {e}")
        print("   ⚠️  Skipping remaining tests")
        return

    # Step 2: Create a new conversation
    print("💬 Step 2: Creating new conversation after deletion...")
    try:
        new_conversation_data = create_conversation(args.base_url, token, influencer_id)
        new_conversation_id = new_conversation_data.get("id")
        new_message_count = new_conversation_data.get("message_count", 0)
        new_user_id = new_conversation_data.get("user_id")
        print(f"   ✅ New conversation created successfully!")
        print(f"   ✅ Conversation ID: {new_conversation_id}")
        print(f"   ✅ User ID: {new_user_id} (same user)")
        print(f"   ✅ Message Count: {new_message_count}")
        if new_user_id != user_id:
            print(f"   ⚠️  WARNING: User ID mismatch! Expected {user_id}, got {new_user_id}")
        print()
    except Exception as e:
        print(f"   ❌ Error creating new conversation: {e}")
        print("   ⚠️  Skipping remaining tests")
        return

    # Step 3: Test POST /conversations endpoint
    print("=" * 70)
    print("📊 Test 1: POST /api/v1/chat/conversations")
    print("=" * 70)
    post_greeting = new_conversation_data.get("greeting_message")
    post_recent = new_conversation_data.get("recent_messages", [])
    
    if post_greeting:
        print("✅ SUCCESS: greeting_message field is present")
        print(f"   Role: {post_greeting.get('role')}")
        print(f"   Content preview: {post_greeting.get('content', '')[:80]}...")
    elif post_recent and len(post_recent) > 0:
        first_msg = post_recent[0]
        if first_msg.get("role") == "assistant":
            print("✅ SUCCESS: greeting message found in recent_messages")
            print(f"   Role: {first_msg.get('role')}")
            print(f"   Content preview: {first_msg.get('content', '')[:80]}...")
        else:
            print("⚠️  WARNING: recent_messages exists but first message is not assistant")
    else:
        print("❌ FAIL: No greeting message found in POST response")
    print()

    # Step 4: Test GET /conversations endpoint
    print("=" * 70)
    print("📊 Test 2: GET /api/v1/chat/conversations")
    print("=" * 70)
    try:
        conversations_list = get_conversations(args.base_url, token, influencer_id)
        conversations = conversations_list.get("conversations", [])
        
        # Find our conversation
        found_conv = None
        for conv in conversations:
            if conv.get("id") == new_conversation_id:
                found_conv = conv
                break
        
        if found_conv:
            print(f"✅ Found conversation in list")
            conv_message_count = found_conv.get("message_count", 0)
            conv_recent = found_conv.get("recent_messages", [])
            print(f"   Message Count: {conv_message_count}")
            
            if conv_recent and len(conv_recent) > 0:
                # Since only 1 message exists, recent_messages should contain the greeting
                first_msg = conv_recent[0] if conv_recent else None
                if first_msg and first_msg.get("role") == "assistant":
                    print("✅ SUCCESS: greeting message found in recent_messages")
                    print(f"   Role: {first_msg.get('role')}")
                    print(f"   Content preview: {first_msg.get('content', '')[:80]}...")
                    print(f"   Total messages in recent_messages: {len(conv_recent)}")
                else:
                    print("⚠️  WARNING: recent_messages exists but first message is not assistant")
            else:
                print("❌ FAIL: recent_messages is empty or missing")
        else:
            print(f"⚠️  WARNING: Conversation {new_conversation_id} not found in list")
    except Exception as e:
        print(f"❌ Error getting conversations: {e}")
    print()

    # Step 5: Test GET /conversations/{id}/messages endpoint
    print("=" * 70)
    print("📊 Test 3: GET /api/v1/chat/conversations/{id}/messages")
    print("=" * 70)
    try:
        messages_data = get_conversation_messages(args.base_url, token, new_conversation_id)
        messages = messages_data.get("messages", [])
        total_messages = messages_data.get("total", 0)
        
        print(f"✅ Retrieved messages successfully")
        print(f"   Total messages: {total_messages}")
        print(f"   Messages in response: {len(messages)}")
        
        if messages:
            # Messages are returned newest first by default
            # Since only 1 message exists (the greeting), it should be the first one
            first_msg = messages[0] if messages else None
            if first_msg and first_msg.get("role") == "assistant":
                print("✅ SUCCESS: greeting message found in messages list")
                print(f"   Role: {first_msg.get('role')}")
                print(f"   Message ID: {first_msg.get('id')}")
                content_preview = first_msg.get("content", "")[:80]
                if content_preview:
                    print(f"   Content preview: {content_preview}...")
            else:
                print("⚠️  WARNING: First message in list is not assistant")
                if first_msg:
                    print(f"   First message role: {first_msg.get('role')}")
        else:
            print("❌ FAIL: messages list is empty")
    except Exception as e:
        print(f"❌ Error getting conversation messages: {e}")
    print()

    # Final summary
    print("=" * 70)
    print("✅ Delete/Recreate Test Complete")
    print("=" * 70)
    print("🎉 All 3 endpoints have been tested for greeting message visibility")
    print()


if __name__ == "__main__":
    main()

