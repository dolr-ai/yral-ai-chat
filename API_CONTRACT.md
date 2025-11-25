# Yral AI Chat API Contracts

Complete API documentation with request/response schemas for all endpoints.

---

## 1. POST /api/v1/chat/conversations
**Create a new conversation with an AI influencer**

### Request
**Headers:**
```
Authorization: Bearer <JWT_TOKEN>
Content-Type: application/json
```

**Body:**
```json
{
  "influencer_id": "uuid-string"
}
```

### Response
**Success (201 Created):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "user_id": "user_123456",
  "influencer": {
    "id": "influencer-uuid",
    "name": "tech_guru_ai",
    "display_name": "Tech Guru AI",
    "avatar_url": "https://cdn.yral.com/avatars/tech_guru.png"
  },
  "created_at": "2024-11-17T10:30:00Z",
  "updated_at": "2024-11-17T10:30:00Z",
  "message_count": 0
}
```

**Errors:**
- `401 Unauthorized`: `{"error": "Unauthorized", "message": "Invalid or missing JWT token"}`
- `404 Not Found`: `{"error": "Not Found", "message": "Influencer not found"}`
- `400 Bad Request`: `{"error": "Bad Request", "message": "influencer_id is required"}`

---

## 2. GET /api/v1/chat/conversations
**List user's conversations**

### Request
**Headers:**
```
Authorization: Bearer <JWT_TOKEN>
```

**Query Parameters:**
```
?limit=20&offset=0&influencer_id=<uuid>
```
- `limit` (optional, default: 20, max: 100)
- `offset` (optional, default: 0)
- `influencer_id` (optional): Filter by specific influencer

### Response
**Success (200 OK):**
```json
{
  "conversations": [
    {
      "id": "conv-uuid-1",
      "user_id": "user_123456",
      "influencer": {
        "id": "influencer-uuid",
        "name": "tech_guru_ai",
        "display_name": "Tech Guru AI",
        "avatar_url": "https://cdn.yral.com/avatars/tech_guru.png"
      },
      "last_message": {
        "content": "That's a great question about AI!",
        "role": "assistant",
        "created_at": "2024-11-17T10:35:00Z"
      },
      "message_count": 12,
      "created_at": "2024-11-17T10:30:00Z",
      "updated_at": "2024-11-17T10:35:00Z"
    }
  ],
  "total": 45,
  "limit": 20,
  "offset": 0
}
```

---

## 3. GET /api/v1/chat/conversations/{conversation_id}/messages
**Get conversation message history**

### Request
**Headers:**
```
Authorization: Bearer <JWT_TOKEN>
```

**Path Parameters:**
- `conversation_id`: UUID of the conversation

**Query Parameters:**
```
?limit=50&offset=0&order=desc
```
- `limit` (optional, default: 50, max: 200)
- `offset` (optional, default: 0)
- `order` (optional, default: desc): "asc" or "desc"

### Response
**Success (200 OK):**
```json
{
  "conversation_id": "conv-uuid-1",
  "messages": [
    {
      "id": "msg-uuid-1",
      "role": "user",
      "content": "What's the latest in AI technology?",
      "content_type": "text",
      "media_urls": [],
      "created_at": "2024-11-17T10:30:00Z"
    },
    {
      "id": "msg-uuid-2",
      "role": "assistant",
      "content": "Great question! The latest developments include...",
      "content_type": "text",
      "media_urls": [],
      "token_count": 156,
      "created_at": "2024-11-17T10:30:05Z"
    },
    {
      "id": "msg-uuid-3",
      "role": "user",
      "content": "Can you analyze this chart?",
      "content_type": "multimodal",
      "media_urls": ["https://cdn.yral.com/uploads/chart123.png"],
      "created_at": "2024-11-17T10:32:00Z"
    }
  ],
  "total": 24,
  "limit": 50,
  "offset": 0
}
```

**Errors:**
- `403 Forbidden`: `{"error": "Forbidden", "message": "Not your conversation"}`
- `404 Not Found`: `{"error": "Not Found", "message": "Conversation not found"}`

---

## 4. POST /api/v1/chat/conversations/{conversation_id}/messages
**Send a message to AI influencer**

### Request
**Headers:**
```
Authorization: Bearer <JWT_TOKEN>
Content-Type: application/json
```

**Path Parameters:**
- `conversation_id`: UUID of the conversation

**Body Examples:**

**A) Text-only message:**
```json
{
  "content": "What's your opinion on blockchain technology?",
  "message_type": "text"
}
```

**B) Text + Image(s):**
```json
{
  "content": "Can you analyze this workout form?",
  "message_type": "multimodal",
  "media_urls": [
    "https://cdn.yral.com/uploads/image1.png",
    "https://cdn.yral.com/uploads/image2.jpg"
  ]
}
```

**C) Image-only (no text):**
```json
{
  "content": "",
  "message_type": "image",
  "media_urls": [
    "https://cdn.yral.com/uploads/workout_photo.jpg"
  ]
}
```

**D) Audio/Voice Note:**
```json
{
  "content": "",
  "message_type": "audio",
  "audio_url": "https://cdn.yral.com/uploads/voice_note_123.mp3",
  "audio_duration_seconds": 15
}
```

**Fields:**
- `content` (optional, max 4000 chars): The message text (can be empty for image-only or audio-only)
- `message_type` (required): One of: "text", "multimodal", "image", "audio"
- `media_urls` (optional, max 10 images): Array of image URLs for multimodal/image input
- `audio_url` (optional): URL to audio file (MP3, M4A, WAV)
- `audio_duration_seconds` (optional): Length of audio in seconds

### Response
**Success (200 OK):**

**Example 1: Text-only response:**
```json
{
  "user_message": {
    "id": "msg-uuid-user",
    "role": "user",
    "content": "What's your opinion on blockchain technology?",
    "message_type": "text",
    "media_urls": [],
    "audio_url": null,
    "created_at": "2024-11-17T10:40:00Z"
  },
  "assistant_message": {
    "id": "msg-uuid-assistant",
    "role": "assistant",
    "content": "Blockchain technology is fascinating! Here's my take...",
    "message_type": "text",
    "media_urls": [],
    "audio_url": null,
    "token_count": 245,
    "created_at": "2024-11-17T10:40:03Z"
  }
}
```

**Example 2: Image-only response:**
```json
{
  "user_message": {
    "id": "msg-uuid-user",
    "role": "user",
    "content": "",
    "message_type": "image",
    "media_urls": ["https://cdn.yral.com/uploads/photo.jpg"],
    "audio_url": null,
    "created_at": "2024-11-17T10:40:00Z"
  },
  "assistant_message": {
    "id": "msg-uuid-assistant",
    "role": "assistant",
    "content": "I can see you're at the gym! Your form looks great, keep it up! 💪",
    "message_type": "text",
    "media_urls": [],
    "audio_url": null,
    "token_count": 28,
    "created_at": "2024-11-17T10:40:03Z"
  }
}
```

**Example 3: Audio/Voice note response:**
```json
{
  "user_message": {
    "id": "msg-uuid-user",
    "role": "user",
    "content": "[Transcribed: Hey, what's a good workout for beginners?]",
    "message_type": "audio",
    "media_urls": [],
    "audio_url": "https://cdn.yral.com/uploads/voice_123.mp3",
    "audio_duration_seconds": 8,
    "created_at": "2024-11-17T10:40:00Z"
  },
  "assistant_message": {
    "id": "msg-uuid-assistant",
    "role": "assistant",
    "content": "Great question bro! For beginners, I recommend:\n1. Push-ups (3 sets of 10)\n2. Bodyweight squats (3 sets of 15)\n3. Planks (3 sets of 30 seconds)\nStart with these and build up gradually! 💪",
    "message_type": "text",
    "media_urls": [],
    "audio_url": null,
    "token_count": 89,
    "created_at": "2024-11-17T10:40:05Z"
  }
}
```

**Errors:**
- `400 Bad Request`: `{"error": "Bad Request", "message": "message_type is required"}`
- `400 Bad Request`: `{"error": "Bad Request", "message": "Invalid message_type. Must be: text, multimodal, image, or audio"}`
- `400 Bad Request`: `{"error": "Bad Request", "message": "content exceeds 4000 characters"}`
- `400 Bad Request`: `{"error": "Bad Request", "message": "Too many media URLs (max 10)"}`
- `400 Bad Request`: `{"error": "Bad Request", "message": "media_urls required for image/multimodal type"}`
- `400 Bad Request`: `{"error": "Bad Request", "message": "audio_url required for audio type"}`
- `400 Bad Request`: `{"error": "Bad Request", "message": "At least content, media_urls, or audio_url must be provided"}`
- `403 Forbidden`: `{"error": "Forbidden", "message": "Not your conversation"}`
- `429 Rate Limit`: `{"error": "Rate Limit", "message": "Too many requests, try again later"}`
- `500 AI Service Error`: `{"error": "AI Service Error", "message": "Failed to generate response"}`
- `500 Audio Transcription Error`: `{"error": "Transcription Error", "message": "Failed to transcribe audio"}`

---

## 5. POST /api/v1/media/upload
**Upload media files (images or audio)**

**Headers:**
```
Authorization: Bearer <JWT_TOKEN>
Content-Type: multipart/form-data
```

**Request Body (multipart/form-data):**
```
file: [binary file data]
type: "image" | "audio"
```

**Success Response (200 OK):**
```json
{
  "url": "https://cdn.yral.com/uploads/user_123456/file_abc123.jpg",
  "type": "image",
  "size": 2456789,
  "mime_type": "image/jpeg",
  "duration_seconds": null,
  "uploaded_at": "2024-11-17T10:45:00Z"
}
```

**For Audio:**
```json
{
  "url": "https://cdn.yral.com/uploads/user_123456/voice_xyz789.mp3",
  "type": "audio",
  "size": 156789,
  "mime_type": "audio/mpeg",
  "duration_seconds": 15,
  "uploaded_at": "2024-11-17T10:45:00Z"
}
```

**Supported File Types:**
- **Images:** JPEG, PNG, WebP, GIF (max 10MB, max 4096x4096px)
- **Audio:** MP3, M4A, WAV, OGG (max 20MB, max 5 minutes)

**Errors:**
- `400 Bad Request`: `{"error": "Bad Request", "message": "No file provided"}`
- `400 Bad Request`: `{"error": "Bad Request", "message": "Unsupported file type"}`
- `413 Payload Too Large`: `{"error": "File Too Large", "message": "File exceeds 10MB limit"}`
- `413 Payload Too Large`: `{"error": "Audio Too Long", "message": "Audio exceeds 5 minute limit"}`

---

## 6. DELETE /api/v1/chat/conversations/{conversation_id}
**Delete a conversation**

### Request
**Headers:**
```
Authorization: Bearer <JWT_TOKEN>
```

**Path Parameters:**
- `conversation_id`: UUID of the conversation

### Response
**Success (200 OK):**
```json
{
  "success": true,
  "message": "Conversation deleted successfully",
  "deleted_conversation_id": "conv-uuid-1",
  "deleted_messages_count": 24
}
```

**Errors:**
- `403 Forbidden`: `{"error": "Forbidden", "message": "Not your conversation"}`
- `404 Not Found`: `{"error": "Not Found", "message": "Conversation not found"}`

---

## 6. GET /api/v1/influencers
**List all active AI influencers**

### Request
**Headers:**
```
Authorization: Bearer <JWT_TOKEN> (Optional)
```

**Query Parameters:**
```
?limit=50&offset=0
```

### Response
**Success (200 OK):**
```json
{
  "influencers": [
    {
      "id": "influencer-uuid-1",
      "name": "tech_guru_ai",
      "display_name": "Tech Guru AI",
      "avatar_url": "https://cdn.yral.com/avatars/tech_guru.png",
      "description": "Your friendly AI companion for all things technology",
      "category": "technology",
      "created_at": "2024-11-01T00:00:00Z"
    },
    {
      "id": "influencer-uuid-2",
      "name": "fitness_coach_ai",
      "display_name": "Fitness Coach AI",
      "avatar_url": "https://cdn.yral.com/avatars/fitness_coach.png",
      "description": "Get personalized fitness advice and motivation",
      "category": "health",
      "created_at": "2024-11-01T00:00:00Z"
    }
  ],
  "total": 15,
  "limit": 50,
  "offset": 0
}
```

---

## 7. GET /api/v1/influencers/{influencer_id}
**Get specific influencer details**

### Request
**Headers:**
```
Authorization: Bearer <JWT_TOKEN> (Optional)
```

**Path Parameters:**
- `influencer_id`: UUID of the influencer

### Response
**Success (200 OK):**
```json
{
  "id": "influencer-uuid-1",
  "name": "tech_guru_ai",
  "display_name": "Tech Guru AI",
  "avatar_url": "https://cdn.yral.com/avatars/tech_guru.png",
  "description": "Your friendly AI companion for all things technology",
  "category": "technology",
  "conversation_count": 1250,
  "created_at": "2024-11-01T00:00:00Z"
}
```

**Errors:**
- `404 Not Found`: `{"error": "Not Found", "message": "Influencer not found"}`

---

## 8. GET /health
**Health check endpoint**

### Response
**Success (200 OK):**
```json
{
  "status": "healthy",
  "timestamp": "2024-11-17T10:40:00Z",
  "services": {
    "database": {
      "status": "up",
      "latency_ms": 5
    },
    "gemini_api": {
      "status": "up",
      "latency_ms": 120
    }
  }
}
```

**Degraded (503 Service Unavailable):**
```json
{
  "status": "unhealthy",
  "timestamp": "2024-11-17T10:40:00Z",
  "services": {
    "database": {
      "status": "down",
      "error": "Connection timeout"
    },
    "gemini_api": {
      "status": "up",
      "latency_ms": 120
    }
  }
}
```

---

## 9. GET /status
**System status endpoint**

### Response
**Success (200 OK):**
```json
{
  "service": "Yral AI Chat API",
  "version": "1.0.0",
  "environment": "production",
  "uptime_seconds": 86400,
  "database": {
    "connected": true,
    "pool_size": 20,
    "active_connections": 5
  },
  "statistics": {
    "total_conversations": 5420,
    "total_messages": 124850,
    "active_influencers": 15
  },
  "timestamp": "2024-11-17T10:40:00Z"
}
```

---

## Common Error Response Format

All endpoints follow this error format:

```json
{
  "error": "Error Type",
  "message": "Human-readable error message",
  "details": {}  // Optional: additional context
}
```

## Authentication

All protected endpoints require a JWT token in the `Authorization` header:

```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

The JWT must contain:
```json
{
  "user_id": "string",
  "exp": 1234567890,
  "iss": "yral_auth"
}
```

