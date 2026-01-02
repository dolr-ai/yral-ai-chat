"""
Gradio Chat App for Yral AI
A streamlined chat interface to talk with AI influencers
"""
import base64
import json
import time
from datetime import datetime

import gradio as gr
import requests

# Configuration
API_BASE_URL = "http://127.0.0.1:8000"


def base64url_encode(data: bytes) -> str:
    """Encode bytes to base64url string without padding"""
    return base64.urlsafe_b64encode(data).decode('utf-8').rstrip('=')


def generate_test_jwt(user_id: str, expires_in_hours: int = 24) -> str:
    """
    Generate a test JWT token for local development
    
    Args:
        user_id: User ID to use in the 'sub' claim
        expires_in_hours: Token expiration time in hours (default: 24)
    
    Returns:
        JWT token string
    """
    # Calculate expiration time
    now = int(time.time())
    exp = now + (expires_in_hours * 3600)
    
    # Create header
    header = {
        "alg": "HS256",
        "typ": "JWT"
    }
    
    # Create payload with required claims
    payload = {
        "iss": "https://auth.yral.com",  # Required issuer
        "sub": user_id,  # Required user ID
        "exp": exp,  # Required expiration
        "iat": now,  # Issued at (optional but standard)
        "aud": "yral-ai-chat-api",  # Audience (optional)
    }
    
    # Encode header and payload
    header_json = json.dumps(header, separators=(',', ':'))
    payload_json = json.dumps(payload, separators=(',', ':'))
    
    header_b64 = base64url_encode(header_json.encode('utf-8'))
    payload_b64 = base64url_encode(payload_json.encode('utf-8'))
    
    # Create a dummy signature (not verified by the auth code)
    signature = base64url_encode(b"dummy_signature_for_testing")
    
    # Combine into JWT token
    return f"{header_b64}.{payload_b64}.{signature}"


# Initialize session state and generate test JWT token
user_id = "test_user_" + datetime.now().strftime("%Y%m%d_%H%M%S")
test_jwt_token = generate_test_jwt(user_id, expires_in_hours=24)

# Session state
session_state = {
    "user_id": user_id,
    "conversation_id": None,
    "influencer_id": None,
    "influencer_name": None,
    "chat_history": [],
    "jwt_token": test_jwt_token  # Auto-generated test token
}


def get_auth_headers():
    """Get authorization headers if token is available"""
    if session_state.get("jwt_token"):
        return {"Authorization": f"Bearer {session_state['jwt_token']}"}
    return {}


def get_influencers():
    """Fetch available influencers"""
    try:
        response = requests.get(f"{API_BASE_URL}/api/v1/influencers")
        response.raise_for_status()
        data = response.json()
        
        # Return list of tuples (display_name, id) for dropdown
        influencers = [(inf["display_name"], inf["id"]) for inf in data.get("influencers", [])]
        return influencers
    except Exception as e:
        print(f"Error fetching influencers: {e}")
        return [("Error loading influencers", None)]


def start_conversation(influencer_id):
    """Initialize a new conversation with selected influencer"""
    if not influencer_id:
        return [], "Please select an influencer first", gr.update(interactive=False)
    
    if not session_state.get("jwt_token"):
        return [], "❌ JWT token required. Set session_state['jwt_token'] programmatically.", gr.update(interactive=False)
    
    try:
        # Create conversation
        headers = {"Content-Type": "application/json", **get_auth_headers()}
        response = requests.post(
            f"{API_BASE_URL}/api/v1/chat/conversations",
            json={"influencer_id": influencer_id},
            headers=headers
        )
        response.raise_for_status()
        data = response.json()
        
        session_state["conversation_id"] = data["id"]
        session_state["influencer_id"] = influencer_id
        session_state["influencer_name"] = data["influencer"]["display_name"]
        
        # Load initial messages (greeting if any)
        history_response = requests.get(
            f"{API_BASE_URL}/api/v1/chat/conversations/{data['id']}/messages",
            params={"limit": 10, "order": "asc"},
            headers=get_auth_headers()
        )
        history_response.raise_for_status()
        history_data = history_response.json()
        
        # Format chat history
        chat_history = []
        for msg in history_data["messages"]:
            if msg["role"] == "user":
                chat_history.append({"role": "user", "content": msg["content"]})
            else:
                chat_history.append({"role": "assistant", "content": msg["content"]})
        
        session_state["chat_history"] = chat_history
        
        status = f"🎉 Started conversation with {session_state['influencer_name']}"
        return chat_history, status, gr.update(interactive=True)
        
    except Exception as e:
        error_msg = f"❌ Error: {e!s}"
        print(error_msg)
        return [], error_msg, gr.update(interactive=False)


def send_message(message, chat_history):
    """Send a text message and get AI response"""
    if not session_state.get("conversation_id"):
        return chat_history, "Please start a conversation first"
    
    if not message or not message.strip():
        return chat_history, ""
    
    try:
        # Send message
        headers = {"Content-Type": "application/json", **get_auth_headers()}
        response = requests.post(
            f"{API_BASE_URL}/api/v1/chat/conversations/{session_state['conversation_id']}/messages",
            json={
                "content": message.strip(),
                "message_type": "text"
            },
            headers=headers
        )
        response.raise_for_status()
        data = response.json()
        
        # Update chat history
        chat_history.append({"role": "user", "content": data["user_message"]["content"]})
        chat_history.append({"role": "assistant", "content": data["assistant_message"]["content"]})
        
        session_state["chat_history"] = chat_history
        
        return chat_history, ""
        
    except Exception as e:
        error_msg = f"Error: {e!s}"
        print(error_msg)
        # Add error to chat
        chat_history.append({"role": "assistant", "content": f"❌ {error_msg}"})
        return chat_history, ""


def send_image_message(image, caption, chat_history):
    """Upload and send image with optional caption"""
    if not session_state.get("conversation_id"):
        chat_history.append({"role": "assistant", "content": "❌ Please start a conversation first"})
        return chat_history, None
    
    if image is None:
        chat_history.append({"role": "assistant", "content": "❌ Please select an image"})
        return chat_history, None
    
    try:
        # Upload image
        with open(image, "rb") as f:
            files = {"file": f}
            data = {"type": "image"}
            upload_response = requests.post(
                f"{API_BASE_URL}/api/v1/media/upload",
                files=files,
                data=data
            )
        upload_response.raise_for_status()
        upload_data = upload_response.json()
        image_url = upload_data["url"]
        
        # Send image message
        message_type = "multimodal" if caption and caption.strip() else "image"
        headers = {"Content-Type": "application/json", **get_auth_headers()}
        response = requests.post(
            f"{API_BASE_URL}/api/v1/chat/conversations/{session_state['conversation_id']}/messages",
            json={
                "content": caption or "",
                "message_type": message_type,
                "media_urls": [image_url]
            },
            headers=headers
        )
        response.raise_for_status()
        data = response.json()
        
        # Update chat history
        user_msg = "🖼️ [Image]"
        if caption:
            user_msg += f" {caption}"
        
        chat_history.append({"role": "user", "content": user_msg})
        chat_history.append({"role": "assistant", "content": data["assistant_message"]["content"]})
        
        session_state["chat_history"] = chat_history
        
        return chat_history, None
        
    except Exception as e:
        error_msg = f"Error uploading image: {e!s}"
        print(error_msg)
        chat_history.append({"role": "assistant", "content": f"❌ {error_msg}"})
        return chat_history, None


def send_audio_message(audio, chat_history):
    """Upload and send audio message"""
    if not session_state.get("conversation_id"):
        chat_history.append({"role": "assistant", "content": "❌ Please start a conversation first"})
        return chat_history, None
    
    if audio is None:
        chat_history.append({"role": "assistant", "content": "❌ Please record or upload audio"})
        return chat_history, None
    
    try:
        # Upload audio
        with open(audio, "rb") as f:
            files = {"file": f}
            data = {"type": "audio"}
            upload_response = requests.post(
                f"{API_BASE_URL}/api/v1/media/upload",
                files=files,
                data=data
            )
        upload_response.raise_for_status()
        upload_data = upload_response.json()
        audio_url = upload_data["url"]
        duration = upload_data.get("duration_seconds", 0)
        
        # Send audio message
        headers = {"Content-Type": "application/json", **get_auth_headers()}
        response = requests.post(
            f"{API_BASE_URL}/api/v1/chat/conversations/{session_state['conversation_id']}/messages",
            json={
                "content": "",
                "message_type": "audio",
                "audio_url": audio_url,
                "audio_duration_seconds": duration
            },
            headers=headers
        )
        response.raise_for_status()
        data = response.json()
        
        # Update chat history
        transcription = data["user_message"]["content"]
        chat_history.append({"role": "user", "content": f"🎤 {transcription}"})
        chat_history.append({"role": "assistant", "content": data["assistant_message"]["content"]})
        
        session_state["chat_history"] = chat_history
        
        return chat_history, None
        
    except Exception as e:
        error_msg = f"Error uploading audio: {e!s}"
        print(error_msg)
        chat_history.append({"role": "assistant", "content": f"❌ {error_msg}"})
        return chat_history, None


def clear_chat():
    """Clear the current chat and reset"""
    session_state["conversation_id"] = None
    session_state["influencer_id"] = None
    session_state["influencer_name"] = None
    session_state["chat_history"] = []
    return [], "Chat cleared. Select an influencer to start a new conversation.", gr.update(interactive=False)


def load_conversation_list():
    """Load list of existing conversations"""
    if not session_state.get("jwt_token"):
        print("Warning: No JWT token set, cannot load conversations")
        return gr.update(choices=[])
    
    try:
        response = requests.get(
            f"{API_BASE_URL}/api/v1/chat/conversations",
            params={"limit": 50},
            headers=get_auth_headers()
        )
        response.raise_for_status()
        data = response.json()
        
        # Format conversations for dropdown
        conversations = []
        for conv in data.get("conversations", []):
            label = f"{conv['influencer']['display_name']} - {conv['message_count']} msgs - {conv['updated_at'][:10]}"
            conversations.append((label, conv["id"]))
        
        return gr.update(choices=conversations)
    except Exception as e:
        print(f"Error loading conversations: {e}")
        return gr.update(choices=[])


def load_existing_conversation(conversation_id):
    """Load an existing conversation"""
    if not conversation_id:
        return [], "Please select a conversation", gr.update(interactive=False)
    
    if not session_state.get("jwt_token"):
        return [], "❌ JWT token required. Set session_state['jwt_token'] programmatically.", gr.update(interactive=False)
    
    try:
        # Get conversation details
        conv_response = requests.get(
            f"{API_BASE_URL}/api/v1/chat/conversations/{conversation_id}/messages",
            params={"limit": 100, "order": "asc"},
            headers=get_auth_headers()
        )
        conv_response.raise_for_status()
        conv_data = conv_response.json()
        
        # Format chat history
        chat_history = []
        for msg in conv_data["messages"]:
            if msg["role"] == "user":
                chat_history.append({"role": "user", "content": msg["content"]})
            else:
                chat_history.append({"role": "assistant", "content": msg["content"]})
        
        session_state["conversation_id"] = conversation_id
        session_state["chat_history"] = chat_history
        
        # Get influencer name from first message
        if conv_data.get("messages"):
            session_state["influencer_name"] = "AI"  # Default name
        
        status = f"✅ Loaded conversation with {conv_data.get('total', 0)} messages"
        return chat_history, status, gr.update(interactive=True)
        
    except Exception as e:
        error_msg = f"❌ Error loading conversation: {e!s}"
        print(error_msg)
        return [], error_msg, gr.update(interactive=False)


def check_api_status():
    """Check if API is available"""
    try:
        response = requests.get(f"{API_BASE_URL}/health", timeout=5)
        response.raise_for_status()
        return "🟢 API Connected"
    except Exception as e:
        return f"🔴 API Offline: {e!s}"


# Create Gradio Interface
with gr.Blocks(title="Yral AI Chat", theme=gr.themes.Soft()) as demo:
    
    # Header
    gr.Markdown(
        """
        # 💬 Yral AI Chat
        Chat with AI influencers powered by advanced language models
        """
    )
    
    # API Status
    api_status = gr.Textbox(
        label="API Status",
        value=check_api_status(),
        interactive=False,
        scale=1
    )
    
    # Main chat interface
    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("### 🎯 Select Influencer")
            
            # Influencer selector
            influencer_dropdown = gr.Dropdown(
                label="Choose an AI Influencer",
                choices=get_influencers(),
                interactive=True
            )
            start_btn = gr.Button("🚀 Start New Chat", variant="primary", size="lg")
            
            gr.Markdown("### 📂 Or Load Existing Chat")
            conversation_dropdown = gr.Dropdown(
                label="Your Conversations",
                choices=[],
                interactive=True
            )
            load_conv_btn = gr.Button("📥 Load Chat", variant="secondary")
            refresh_conv_btn = gr.Button("🔄 Refresh List", size="sm")
            
            # Clear button
            clear_btn = gr.Button("🗑️ Clear Chat", variant="stop")
            
            # Status message
            status_msg = gr.Textbox(
                label="Status",
                interactive=False,
                lines=2
            )
        
        with gr.Column(scale=3):
            # Chat interface
            chatbot = gr.Chatbot(
                label="Chat",
                height=500,
                show_label=False,
                avatar_images=(None, "🤖")
            )
            
            # Message input
            with gr.Row():
                msg_input = gr.Textbox(
                    label="Message",
                    placeholder="Type your message here...",
                    scale=5,
                    show_label=False,
                    interactive=False
                )
                send_btn = gr.Button("📤 Send", variant="primary", scale=1, interactive=False)
            
            # Multimodal inputs
            with gr.Accordion("📎 Send Image or Audio", open=False):
                with gr.Tab("🖼️ Image"):
                    image_input = gr.Image(
                        label="Upload Image",
                        type="filepath"
                    )
                    image_caption = gr.Textbox(
                        label="Caption (optional)",
                        placeholder="Ask a question about the image..."
                    )
                    send_image_btn = gr.Button("📤 Send Image", variant="primary")
                
                with gr.Tab("🎤 Audio"):
                    audio_input = gr.Audio(
                        label="Record or Upload Audio",
                        type="filepath"
                    )
                    send_audio_btn = gr.Button("📤 Send Audio", variant="primary")
    
    # Footer
    gr.Markdown(
        f"""
        ---
        **API:** `{API_BASE_URL}` | **User ID:** `{session_state['user_id']}`
        """
    )
    
    # Event handlers
    start_btn.click(
        start_conversation,
        inputs=[influencer_dropdown],
        outputs=[chatbot, status_msg, msg_input]
    ).then(
        lambda: gr.update(interactive=True),
        outputs=[send_btn]
    )
    
    send_btn.click(
        send_message,
        inputs=[msg_input, chatbot],
        outputs=[chatbot, msg_input]
    )
    
    msg_input.submit(
        send_message,
        inputs=[msg_input, chatbot],
        outputs=[chatbot, msg_input]
    )
    
    send_image_btn.click(
        send_image_message,
        inputs=[image_input, image_caption, chatbot],
        outputs=[chatbot, image_input]
    )
    
    send_audio_btn.click(
        send_audio_message,
        inputs=[audio_input, chatbot],
        outputs=[chatbot, audio_input]
    )
    
    clear_btn.click(
        clear_chat,
        outputs=[chatbot, status_msg, msg_input]
    ).then(
        lambda: gr.update(interactive=False),
        outputs=[send_btn]
    )
    
    refresh_conv_btn.click(
        load_conversation_list,
        outputs=[conversation_dropdown]
    )
    
    load_conv_btn.click(
        load_existing_conversation,
        inputs=[conversation_dropdown],
        outputs=[chatbot, status_msg, msg_input]
    ).then(
        lambda: gr.update(interactive=True),
        outputs=[send_btn]
    )


if __name__ == "__main__":
    print("🚀 Starting Yral AI Chat App...")
    print(f"📡 API URL: {API_BASE_URL}")
    print("🌐 Make sure your API server is running!")
    print("\nStarting chat app on http://localhost:7861")
    demo.launch(server_name="0.0.0.0", server_port=7861, share=False)
