"""
Gradio Demo for Yral AI Chat API
Tests all endpoints in a user-friendly interface
"""
import gradio as gr
import requests
import json
from typing import List, Tuple

# Configuration
API_BASE_URL = "http://localhost:8000"

# Global state
current_user_id = "demo_user_123"
current_conversation_id = None
current_influencer_id = None


def format_json(data):
    """Pretty print JSON"""
    return json.dumps(data, indent=2)


def get_influencers() -> Tuple[str, str]:
    """Step 1: Get list of influencers"""
    try:
        response = requests.get(f"{API_BASE_URL}/api/v1/influencers")
        response.raise_for_status()
        data = response.json()
        
        # Format for display
        influencers_list = []
        for inf in data.get('influencers', []):
            influencers_list.append(
                f"• {inf['display_name']} ({inf['name']})\n"
                f"  ID: {inf['id']}\n"
                f"  Category: {inf['category']}\n"
                f"  {inf['description']}\n"
            )
        
        return "\n".join(influencers_list), format_json(data)
    except Exception as e:
        return f"Error: {str(e)}", "{}"


def create_conversation(influencer_id: str) -> Tuple[str, str, str]:
    """Step 2: Create or get conversation"""
    global current_conversation_id, current_influencer_id
    
    if not influencer_id.strip():
        return "Please enter an influencer ID", None, ""
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/api/v1/chat/conversations",
            json={"influencer_id": influencer_id.strip()},
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()
        data = response.json()
        
        current_conversation_id = data['id']
        current_influencer_id = influencer_id.strip()
        
        status = (
            f"✓ Conversation Created!\n"
            f"Conversation ID: {data['id']}\n"
            f"User ID: {data['user_id']}\n"
            f"Influencer: {data['influencer']['display_name']}\n"
            f"Messages: {data['message_count']}"
        )
        
        return status, format_json(data), data['id']
    except Exception as e:
        return f"Error: {str(e)}", "{}", ""


def send_text_message(conversation_id: str, message: str) -> Tuple[str, str, List]:
    """Step 3: Send text message"""
    if not conversation_id.strip():
        return "Please create a conversation first", None, []
    
    if not message.strip():
        return "Please enter a message", None, []
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/api/v1/chat/conversations/{conversation_id.strip()}/messages",
            json={
                "content": message,
                "message_type": "text"
            },
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()
        data = response.json()
        
        # Format chat history - use dict format for Gradio 4.x+
        chat_history = [
            {"role": "user", "content": data['user_message']['content']},
            {"role": "assistant", "content": data['assistant_message']['content']}
        ]
        
        status = (
            f"✓ Message Sent!\n"
            f"User: {data['user_message']['content'][:50]}...\n"
            f"AI Response: {data['assistant_message']['content'][:100]}...\n"
            f"Tokens: {data['assistant_message'].get('token_count', 'N/A')}"
        )
        
        return status, format_json(data), chat_history
    except Exception as e:
        return f"Error: {str(e)}", "{}", []


def upload_media(file, media_type: str) -> Tuple[str, str]:
    """Upload image or audio"""
    if file is None:
        return "Please select a file", None
    
    try:
        with open(file.name, 'rb') as f:
            files = {'file': f}
            data = {'type': media_type}
            response = requests.post(
                f"{API_BASE_URL}/api/v1/media/upload",
                files=files,
                data=data
            )
        response.raise_for_status()
        result = response.json()
        
        status = (
            f"✓ {media_type.capitalize()} Uploaded!\n"
            f"URL: {result['url']}\n"
            f"Size: {result['size']} bytes\n"
            f"Type: {result['mime_type']}"
        )
        if result.get('duration_seconds'):
            status += f"\nDuration: {result['duration_seconds']}s"
        
        return status, result['url']
    except Exception as e:
        return f"Error: {str(e)}", ""


def send_image_message(conversation_id: str, image_url: str, caption: str) -> Tuple[str, str]:
    """Send image message"""
    if not conversation_id.strip():
        return "Please create a conversation first", None
    
    if not image_url.strip():
        return "Please upload an image first", None
    
    try:
        message_type = "multimodal" if caption.strip() else "image"
        response = requests.post(
            f"{API_BASE_URL}/api/v1/chat/conversations/{conversation_id.strip()}/messages",
            json={
                "content": caption,
                "message_type": message_type,
                "media_urls": [image_url.strip()]
            },
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()
        data = response.json()
        
        status = (
            f"✓ Image Message Sent!\n"
            f"AI Response: {data['assistant_message']['content'][:200]}..."
        )
        
        return status, format_json(data)
    except Exception as e:
        return f"Error: {str(e)}", "{}"


def send_audio_message(conversation_id: str, audio_url: str, duration: int) -> Tuple[str, str]:
    """Send audio message"""
    if not conversation_id.strip():
        return "Please create a conversation first", None
    
    if not audio_url.strip():
        return "Please upload audio first", None
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/api/v1/chat/conversations/{conversation_id.strip()}/messages",
            json={
                "content": "",
                "message_type": "audio",
                "audio_url": audio_url.strip(),
                "audio_duration_seconds": duration
            },
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()
        data = response.json()
        
        status = (
            f"✓ Audio Message Sent!\n"
            f"Transcription: {data['user_message']['content']}\n"
            f"AI Response: {data['assistant_message']['content'][:200]}..."
        )
        
        return status, format_json(data)
    except Exception as e:
        return f"Error: {str(e)}", "{}"


def get_message_history(conversation_id: str, limit: int) -> Tuple[str, str, List]:
    """Get conversation history"""
    if not conversation_id.strip():
        return "Please create a conversation first", None, []
    
    try:
        response = requests.get(
            f"{API_BASE_URL}/api/v1/chat/conversations/{conversation_id.strip()}/messages",
            params={"limit": limit, "order": "asc"}
        )
        response.raise_for_status()
        data = response.json()
        
        # Format for chat display - use dict format for Gradio 4.x+
        chat_history = []
        for msg in data['messages']:
            chat_history.append({
                "role": msg['role'],
                "content": msg['content'] or "(empty message)"
            })
        
        status = f"✓ Loaded {data['total']} messages"
        
        return status, format_json(data), chat_history
    except Exception as e:
        return f"Error: {str(e)}", "{}", []


def list_conversations(limit: int) -> Tuple[str, str]:
    """List all user conversations"""
    try:
        response = requests.get(
            f"{API_BASE_URL}/api/v1/chat/conversations",
            params={"limit": limit}
        )
        response.raise_for_status()
        data = response.json()
        
        # Format for display
        conv_list = []
        for conv in data.get('conversations', []):
            last_msg = conv.get('last_message', {})
            conv_list.append(
                f"• Conversation with {conv['influencer']['display_name']}\n"
                f"  ID: {conv['id']}\n"
                f"  Messages: {conv['message_count']}\n"
                f"  Last: {last_msg.get('content', 'N/A')[:50]}...\n"
                f"  Updated: {conv['updated_at']}\n"
            )
        
        status = f"✓ Found {data['total']} conversations"
        
        return status + "\n\n" + "\n".join(conv_list), format_json(data)
    except Exception as e:
        return f"Error: {str(e)}", "{}"


def delete_conversation(conversation_id: str) -> Tuple[str, str]:
    """Delete a conversation"""
    if not conversation_id.strip():
        return "Please enter a conversation ID", None
    
    try:
        response = requests.delete(
            f"{API_BASE_URL}/api/v1/chat/conversations/{conversation_id.strip()}"
        )
        response.raise_for_status()
        data = response.json()
        
        status = (
            f"✓ Conversation Deleted!\n"
            f"Deleted {data['deleted_messages_count']} messages"
        )
        
        return status, format_json(data)
    except Exception as e:
        return f"Error: {str(e)}", "{}"


def check_health() -> Tuple[str, str]:
    """Check API health"""
    try:
        response = requests.get(f"{API_BASE_URL}/health")
        response.raise_for_status()
        data = response.json()
        
        status = f"✓ API Status: {data['status'].upper()}"
        for service, info in data.get('services', {}).items():
            status += f"\n{service}: {info['status']}"
            if 'latency_ms' in info:
                status += f" ({info['latency_ms']}ms)"
        
        return status, format_json(data)
    except Exception as e:
        return f"Error: {str(e)}", "{}"


# Create Gradio Interface
with gr.Blocks(title="Yral AI Chat API Demo") as demo:
    gr.Markdown("# 🤖 Yral AI Chat API Demo")
    gr.Markdown(f"Testing API at: `{API_BASE_URL}`")
    
    # Health Check
    with gr.Accordion("🏥 Health Check", open=False):
        with gr.Row():
            health_btn = gr.Button("Check API Health", variant="secondary")
        health_status = gr.Textbox(label="Status", lines=3)
        health_json = gr.JSON(label="Response")
        health_btn.click(check_health, outputs=[health_status, health_json])
    
    gr.Markdown("---")
    gr.Markdown("## 📋 Step-by-Step Flow")
    
    # Step 1: Browse Influencers
    with gr.Accordion("1️⃣ Browse AI Influencers", open=True):
        gr.Markdown("First, let's see what AI influencers are available")
        get_inf_btn = gr.Button("Get Influencers", variant="primary")
        inf_display = gr.Textbox(label="Available Influencers", lines=10)
        inf_json = gr.JSON(label="Raw Response")
        get_inf_btn.click(get_influencers, outputs=[inf_display, inf_json])
    
    # Step 2: Create Conversation
    with gr.Accordion("2️⃣ Create Conversation", open=True):
        gr.Markdown("Copy an influencer ID from above and create a conversation")
        with gr.Row():
            inf_id_input = gr.Textbox(label="Influencer ID", placeholder="paste-uuid-here")
            create_conv_btn = gr.Button("Create Conversation", variant="primary")
        conv_status = gr.Textbox(label="Status", lines=3)
        conv_id_output = gr.Textbox(label="Conversation ID (save this!)")
        conv_json = gr.JSON(label="Response")
        create_conv_btn.click(
            create_conversation, 
            inputs=[inf_id_input],
            outputs=[conv_status, conv_json, conv_id_output]
        )
    
    # Step 2.5: View Initial Greeting
    with gr.Accordion("2️⃣ 🎉 View Initial Greeting", open=True):
        gr.Markdown("""
        After creating a conversation, the AI influencer may send an automatic greeting message.
        Use this section to view it!
        """)
        with gr.Row():
            conv_id_greeting = gr.Textbox(label="Conversation ID", placeholder="paste-conversation-id")
            load_greeting_btn = gr.Button("Load Message History", variant="primary")
        greeting_status = gr.Textbox(label="Status", lines=2)
        greeting_chat = gr.Chatbot(label="Initial Greeting Preview", height=250)
        greeting_json = gr.JSON(label="Full Response")
        load_greeting_btn.click(
            get_message_history,
            inputs=[conv_id_greeting, gr.State(10)],
            outputs=[greeting_status, greeting_json, greeting_chat]
        )
    
    # Step 3: Send Text Messages
    with gr.Accordion("3️⃣ Send Text Messages", open=True):
        gr.Markdown("Chat with the AI influencer")
        conv_id_text = gr.Textbox(label="Conversation ID", placeholder="paste-conversation-id")
        chatbot = gr.Chatbot(label="Chat History", height=300)
        msg_input = gr.Textbox(label="Your Message", placeholder="Type your message here...")
        send_btn = gr.Button("Send Message", variant="primary")
        msg_status = gr.Textbox(label="Status", lines=2)
        msg_json = gr.JSON(label="Response")
        
        send_btn.click(
            send_text_message,
            inputs=[conv_id_text, msg_input],
            outputs=[msg_status, msg_json, chatbot]
        )
    
    # Step 4: Send Image Messages
    with gr.Accordion("4️⃣ Send Image Messages", open=False):
        gr.Markdown("Upload an image and get AI analysis")
        with gr.Row():
            image_file = gr.File(label="Select Image", file_types=["image"])
            upload_img_btn = gr.Button("Upload Image")
        img_upload_status = gr.Textbox(label="Upload Status", lines=2)
        img_url_output = gr.Textbox(label="Image URL")
        upload_img_btn.click(
            upload_media,
            inputs=[image_file, gr.State("image")],
            outputs=[img_upload_status, img_url_output]
        )
        
        gr.Markdown("Now send the image to the AI")
        conv_id_img = gr.Textbox(label="Conversation ID")
        img_caption = gr.Textbox(label="Caption (optional)", placeholder="What do you want to ask about this image?")
        send_img_btn = gr.Button("Send Image Message", variant="primary")
        img_msg_status = gr.Textbox(label="Status", lines=3)
        img_msg_json = gr.JSON(label="Response")
        send_img_btn.click(
            send_image_message,
            inputs=[conv_id_img, img_url_output, img_caption],
            outputs=[img_msg_status, img_msg_json]
        )
    
    # Step 5: Send Audio Messages
    with gr.Accordion("5️⃣ Send Audio Messages", open=False):
        gr.Markdown("Upload audio and get transcription + AI response")
        with gr.Row():
            audio_file = gr.File(label="Select Audio", file_types=["audio"])
            upload_audio_btn = gr.Button("Upload Audio")
        audio_upload_status = gr.Textbox(label="Upload Status", lines=2)
        audio_url_output = gr.Textbox(label="Audio URL")
        upload_audio_btn.click(
            upload_media,
            inputs=[audio_file, gr.State("audio")],
            outputs=[audio_upload_status, audio_url_output]
        )
        
        gr.Markdown("Send the audio to the AI")
        conv_id_audio = gr.Textbox(label="Conversation ID")
        audio_duration = gr.Number(label="Duration (seconds)", value=0)
        send_audio_btn = gr.Button("Send Audio Message", variant="primary")
        audio_msg_status = gr.Textbox(label="Status", lines=3)
        audio_msg_json = gr.JSON(label="Response")
        send_audio_btn.click(
            send_audio_message,
            inputs=[conv_id_audio, audio_url_output, audio_duration],
            outputs=[audio_msg_status, audio_msg_json]
        )
    
    # Step 6: View History
    with gr.Accordion("6️⃣ View Message History", open=False):
        gr.Markdown("Load full conversation history")
        with gr.Row():
            conv_id_history = gr.Textbox(label="Conversation ID")
            history_limit = gr.Slider(label="Limit", minimum=10, maximum=200, value=50, step=10)
        get_history_btn = gr.Button("Get History", variant="primary")
        history_status = gr.Textbox(label="Status")
        history_chat = gr.Chatbot(label="Full History", height=400)
        history_json = gr.JSON(label="Response")
        get_history_btn.click(
            get_message_history,
            inputs=[conv_id_history, history_limit],
            outputs=[history_status, history_json, history_chat]
        )
    
    # Step 7: List Conversations
    with gr.Accordion("7️⃣ List All Conversations", open=False):
        gr.Markdown("See all your conversations")
        with gr.Row():
            list_limit = gr.Slider(label="Limit", minimum=5, maximum=50, value=20, step=5)
            list_conv_btn = gr.Button("List Conversations", variant="primary")
        list_status = gr.Textbox(label="Conversations", lines=15)
        list_json = gr.JSON(label="Response")
        list_conv_btn.click(
            list_conversations,
            inputs=[list_limit],
            outputs=[list_status, list_json]
        )
    
    # Step 8: Delete Conversation
    with gr.Accordion("8️⃣ Delete Conversation", open=False):
        gr.Markdown("⚠️ This will permanently delete the conversation and all messages")
        with gr.Row():
            conv_id_delete = gr.Textbox(label="Conversation ID")
            delete_btn = gr.Button("Delete Conversation", variant="stop")
        delete_status = gr.Textbox(label="Status", lines=2)
        delete_json = gr.JSON(label="Response")
        delete_btn.click(
            delete_conversation,
            inputs=[conv_id_delete],
            outputs=[delete_status, delete_json]
        )


if __name__ == "__main__":
    print("🚀 Starting Gradio Demo...")
    print(f"📡 API URL: {API_BASE_URL}")
    print("🌐 Make sure your API server is running!")
    print("\nStarting demo on http://localhost:7860")
    demo.launch(server_name="0.0.0.0", server_port=7860, share=True)