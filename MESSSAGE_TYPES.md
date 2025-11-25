# Message Types Summary - Yral AI Chat

Complete guide for all supported message input and output types.

---

## User Input Types

The API supports 4 types of user inputs:

### 1. Text-Only Message
**Use Case:** User types a message

**Request:**
```json
{
  "content": "What's your opinion on blockchain technology?",
  "message_type": "text"
}
```

**Mobile Implementation:**
- User types in text input field
- User taps send button
- POST message directly

---

### 2. Text + Image(s) (Multimodal)
**Use Case:** User sends text with one or more images

**Flow:**
1. User selects image(s) from gallery/camera
2. Upload images: `POST /api/v1/media/upload`
3. Get image URLs
4. Send message with text + URLs

**Request:**
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

**Mobile Implementation:**
- User types message
- User taps camera/gallery icon
- User selects images (max 10)
- App uploads images in background
- POST message with text + image URLs

---

### 3. Image-Only (No Text)
**Use Case:** User sends image(s) without any text

**Flow:**
1. User selects image(s)
2. Upload images
3. Send message with empty content

**Request:**
```json
{
  "content": "",
  "message_type": "image",
  "media_urls": [
    "https://cdn.yral.com/uploads/workout_photo.jpg"
  ]
}
```

**Mobile Implementation:**
- User taps camera/gallery icon (without typing)
- User selects image
- App uploads image
- POST message with empty text + image URL
- UI shows image in chat bubble

---

### 4. Audio/Voice Note
**Use Case:** User records and sends a voice message

**Flow:**
1. User taps and holds microphone button
2. User speaks (recording)
3. User releases button (stop recording)
4. Upload audio file
5. Send message with audio URL

**Request:**
```json
{
  "content": "",
  "message_type": "audio",
  "audio_url": "https://cdn.yral.com/uploads/voice_note_123.mp3",
  "audio_duration_seconds": 15
}
```

**Mobile Implementation:**
- User taps/holds mic button
- App records audio (show waveform/timer)
- User releases or taps stop
- App uploads audio file
- POST message with audio URL
- UI shows audio player in chat bubble

---

## AI Response Types

The AI (Gemini) will ALWAYS respond with text. The response format is:

```json
{
  "assistant_message": {
    "id": "msg-uuid",
    "role": "assistant",
    "content": "AI response text here...",
    "message_type": "text",
    "media_urls": [],
    "audio_url": null,
    "token_count": 125,
    "created_at": "2024-11-18T10:40:05Z"
  }
}
```

**Key Points:**
- AI always responds with text (no images or audio from AI in MVP)
- AI can understand and analyze images sent by user
- AI can understand audio after transcription
- Response includes token count for analytics

---

## Complete Message Flow Examples

### Example 1: Text Chat

```
User Types: "What's a good workout for abs?"
Mobile App → POST /api/v1/chat/conversations/{id}/messages
{
  "content": "What's a good workout for abs?",
  "message_type": "text"
}

Response:
{
  "user_message": { ... user message data ... },
  "assistant_message": {
    "content": "Great question! Here's an effective ab workout:
                1. Crunches - 3 sets of 15 reps
                2. Planks - 3 sets of 45 seconds
                3. Russian Twists - 3 sets of 20 reps
                Try this 3 times per week! 💪"
  }
}
```

---

### Example 2: Image Analysis

```
User Action: Takes photo of their workout form
Mobile App → POST /api/v1/media/upload (upload photo)
Response: { "url": "https://cdn.yral.com/uploads/photo123.jpg" }

User Types: "How's my form?"
Mobile App → POST /api/v1/chat/conversations/{id}/messages
{
  "content": "How's my form?",
  "message_type": "multimodal",
  "media_urls": ["https://cdn.yral.com/uploads/photo123.jpg"]
}

Response:
{
  "user_message": { ... with image ... },
  "assistant_message": {
    "content": "Looking at your squat form:
                ✅ Good: Depth is solid, chest is up
                ⚠️ Watch: Keep knees aligned with toes
                💡 Tip: Try pointing toes slightly outward
                Keep crushing it bro! 💪"
  }
}
```

---

### Example 3: Image-Only (No Text)

```
User Action: Sends photo without typing anything
Mobile App → POST /api/v1/media/upload
Response: { "url": "https://cdn.yral.com/uploads/gym_photo.jpg" }

Mobile App → POST /api/v1/chat/conversations/{id}/messages
{
  "content": "",
  "message_type": "image",
  "media_urls": ["https://cdn.yral.com/uploads/gym_photo.jpg"]
}

Response:
{
  "user_message": { ... image only ... },
  "assistant_message": {
    "content": "I can see you're at the gym! Looking strong bro! 
                What are you working on today? 💪🔥"
  }
}
```

---

### Example 4: Voice Note

```
User Action: Records 10-second voice message saying "Hey Kaio, what's the best time to workout?"
Mobile App → Records audio to file (voice_123.mp3)
Mobile App → POST /api/v1/media/upload
Response: { 
  "url": "https://cdn.yral.com/uploads/voice_123.mp3",
  "duration_seconds": 10
}

Mobile App → POST /api/v1/chat/conversations/{id}/messages
{
  "content": "",
  "message_type": "audio",
  "audio_url": "https://cdn.yral.com/uploads/voice_123.mp3",
  "audio_duration_seconds": 10
}

Backend Process:
1. Receives audio file
2. Transcribes using Gemini/Whisper: "Hey Kaio, what's the best time to workout?"
3. Sends transcribed text to Gemini for response
4. Stores both audio URL and transcription

Response:
{
  "user_message": {
    "content": "[Transcribed: Hey Kaio, what's the best time to workout?]",
    "message_type": "audio",
    "audio_url": "https://cdn.yral.com/uploads/voice_123.mp3"
  },
  "assistant_message": {
    "content": "Hey bro! Great question! 🌅
                The best time to workout depends on YOU:
                
                🌄 Morning (6-9 AM): 
                - Boosts energy for the day
                - Gym is less crowded
                - Builds discipline
                
                🌆 Evening (5-8 PM):
                - Peak physical performance
                - More strength and power
                - Great for stress relief
                
                Pick what fits YOUR schedule and stick to it! 
                Consistency > timing! 💯"
  }
}
```

---

## Validation Rules

### Text Messages:
- `content`: Optional (can be empty for image/audio-only)
- Max length: 4000 characters
- Min length: 0 characters (for image/audio-only)

### Image Messages:
- `media_urls`: Required for "image" and "multimodal" types
- Max images: 10 per message
- Supported formats: JPEG, PNG, WebP, GIF
- Max file size: 10MB per image
- Max resolution: 4096x4096px

### Audio Messages:
- `audio_url`: Required for "audio" type
- Supported formats: MP3, M4A, WAV, OGG
- Max file size: 20MB
- Max duration: 5 minutes (300 seconds)
- Will be transcribed automatically

### General Rules:
- At least ONE of `content`, `media_urls`, or `audio_url` must be provided
- `message_type` is required
- Valid message_types: "text", "multimodal", "image", "audio"

---

## Error Handling

### Missing Required Fields:
```json
{
  "error": "Bad Request",
  "message": "message_type is required"
}
```

### Invalid Message Type:
```json
{
  "error": "Bad Request",
  "message": "Invalid message_type. Must be: text, multimodal, image, or audio"
}
```

### Image Type Without Images:
```json
{
  "error": "Bad Request",
  "message": "media_urls required for image/multimodal type"
}
```

### Audio Type Without Audio:
```json
{
  "error": "Bad Request",
  "message": "audio_url required for audio type"
}
```

### Empty Message:
```json
{
  "error": "Bad Request",
  "message": "At least content, media_urls, or audio_url must be provided"
}
```

### Too Many Images:
```json
{
  "error": "Bad Request",
  "message": "Too many media URLs (max 10)"
}
```

### Content Too Long:
```json
{
  "error": "Bad Request",
  "message": "content exceeds 4000 characters"
}
```

---

## Mobile UI Guidelines

### Text Message:
```
┌─────────────────────────┐
│ User: "What's a good    │
│        workout?"        │
└─────────────────────────┘

┌─────────────────────────┐
│ AI: "Try these:         │
│     1. Push-ups         │
│     2. Squats           │
│     3. Planks 💪"       │
└─────────────────────────┘
```

### Image Message:
```
┌─────────────────────────┐
│ User: [Image Preview]   │
│       "How's my form?"  │
└─────────────────────────┘

┌─────────────────────────┐
│ AI: "Great form bro! ✅ │
│      Keep chest up..."  │
└─────────────────────────┘
```

### Audio Message:
```
┌─────────────────────────┐
│ User: 🎤 [====>] 0:15   │
│       [Play Button]     │
└─────────────────────────┘

┌─────────────────────────┐
│ AI: "Hey bro! Morning   │
│      workouts are..."   │
└─────────────────────────┘
```

---

## Database Schema for Messages

```sql
CREATE TYPE message_type_enum AS ENUM ('text', 'multimodal', 'image', 'audio');

CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT,
    message_type message_type_enum NOT NULL,
    media_urls JSONB DEFAULT '[]',
    audio_url TEXT,
    audio_duration_seconds INTEGER,
    token_count INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);
```

---

## Implementation Checklist for Backend

- [ ] Support all 4 message types (text, multimodal, image, audio)
- [ ] Validate message_type field
- [ ] Validate required fields based on message_type
- [ ] Image upload endpoint with format/size validation
- [ ] Audio upload endpoint with format/size validation
- [ ] Audio transcription (using Gemini or Whisper API)
- [ ] Store transcription in content field for audio messages
- [ ] Gemini multimodal integration for image analysis
- [ ] Proper error messages for each validation case
- [ ] Token counting for all responses
- [ ] Store all message types in database correctly

