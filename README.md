# Yral AI Chat API

A FastAPI-based REST API for multimodal AI chat with personalized influencer personas powered by Google Gemini.

## Features

- Multiple AI influencer personas with unique personalities
- Multimodal support (text, images, audio)
- Conversation history and context awareness
- JWT-based authentication
- PostgreSQL database with async operations
- Media upload and storage
- RESTful API design

## Tech Stack

- **Framework**: FastAPI 0.104.1
- **Database**: PostgreSQL with asyncpg
- **AI Model**: Google Gemini 1.5 Pro
- **Authentication**: JWT (PyJWT)
- **Server**: Uvicorn with async support
- **ORM**: SQLAlchemy 2.0 (async)

## Project Structure

```
yral-ai-chat/
├── src/
│   ├── api/
│   │   └── v1/
│   │       ├── chat.py           # Chat endpoints
│   │       ├── influencers.py    # Influencer endpoints
│   │       ├── media.py          # Media upload endpoints
│   │       └── health.py         # Health check endpoints
│   ├── auth/
│   │   └── jwt_auth.py           # JWT authentication
│   ├── db/
│   │   ├── base.py               # Database connection
│   │   ├── repositories/         # Data access layer
│   │   │   ├── conversation_repository.py
│   │   │   ├── message_repository.py
│   │   │   └── influencer_repository.py
│   │   └── schemas/              # Database schemas
│   ├── services/
│   │   ├── chat_service.py       # Business logic
│   │   ├── gemini_client.py      # Gemini API client
│   │   ├── influencer_service.py # Influencer service
│   │   └── storage_service.py    # File storage service
│   ├── models/
│   │   ├── entities.py           # Domain models
│   │   ├── requests.py           # API request models
│   │   └── responses.py          # API response models
│   ├── core/
│   │   ├── exceptions.py         # Custom exceptions
│   │   └── logging.py            # Logging configuration
│   ├── config.py                 # Configuration management
│   └── main.py                   # Application entry point
├── migrations/
│   ├── 001_init_schema.sql       # Database schema
│   └── 002_seed_influencers.sql  # Initial data
├── scripts/
│   └── setup_db.sh               # Database setup script
├── tests/                        # Test files
├── uploads/                      # Media storage
├── logs/                         # Application logs
├── requirements.txt              # Python dependencies
├── .env                          # Environment variables
└── full_test.sh                  # Integration test script
```

## Database Schema

### Tables

**ai_influencers**
- Stores AI persona definitions
- Fields: id, name, display_name, avatar_url, description, category, system_instructions, personality_traits

**conversations**
- Links users with AI influencers
- One conversation per user-influencer pair
- Fields: id, user_id, influencer_id, created_at, updated_at

**messages**
- Individual chat messages
- Fields: id, conversation_id, role (user/assistant), content, message_type, media_urls, audio_url, token_count

### Relationships

```
ai_influencers (1) ──< (N) conversations (1) ──< (N) messages
```

## API Endpoints

### Authentication
All endpoints except health check and influencer listing require JWT authentication via Bearer token.

### Influencers

**GET /api/v1/influencers**
- List all active AI influencers
- Query params: limit, offset
- Authentication: Optional

**GET /api/v1/influencers/{id}**
- Get specific influencer details
- Authentication: Optional

### Conversations

**POST /api/v1/chat/conversations**
- Create new conversation with an influencer
- Body: `{"influencer_id": "uuid"}`
- Returns existing conversation if already exists
- Authentication: Required

**GET /api/v1/chat/conversations**
- List user's conversations
- Query params: limit, offset, influencer_id
- Returns conversations with last message preview
- Authentication: Required

**DELETE /api/v1/chat/conversations/{id}**
- Delete conversation and all messages
- Authentication: Required

### Messages

**POST /api/v1/chat/conversations/{id}/messages**
- Send message to AI influencer
- Supports text, multimodal (text+images), image-only, audio
- Returns both user message and AI response
- Authentication: Required

Request body examples:

```json
// Text message
{
  "content": "Your message here",
  "message_type": "text"
}

// Multimodal (text + images)
{
  "content": "Analyze this image",
  "message_type": "multimodal",
  "media_urls": ["https://example.com/image.jpg"]
}

// Audio message
{
  "message_type": "audio",
  "audio_url": "https://example.com/audio.mp3",
  "audio_duration_seconds": 15
}
```

**GET /api/v1/chat/conversations/{id}/messages**
- Get conversation message history
- Query params: limit, offset, order (asc/desc)
- Authentication: Required

### Media

**POST /api/v1/media/upload**
- Upload image or audio file
- Content-Type: multipart/form-data
- Returns URL for use in messages
- Authentication: Required

### Health

**GET /health**
- Health check endpoint
- Returns database and Gemini API status
- Authentication: Not required

## Setup Instructions

### Prerequisites

- Python 3.12+
- PostgreSQL 14+
- Google Gemini API key

### Installation

1. Clone repository and activate virtual environment:
```bash
cd /root/yral-ai-chat
source venv/bin/activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Setup PostgreSQL database:
```bash
chmod +x scripts/setup_db.sh
./scripts/setup_db.sh
```

4. Run database migrations:
```bash
source .env 
PGPASSWORD=$(grep DATABASE_URL .env | cut -d':' -f3 | cut -d'@' -f1) psql -U yral_chat_user -h localhost -d yral_chat -f migrations/001_init_schema.sql
PGPASSWORD=$(grep DATABASE_URL .env | cut -d':' -f3 | cut -d'@' -f1) psql -U yral_chat_user -h localhost -d yral_chat -f migrations/002_seed_influencers.sql
```

5. Create `.env` file from `.env.example`:
```bash
cp .env.example .env
# Edit .env with your actual configuration values
```

**Note:** Never commit `.env` to version control. The `.env` file is already in `.gitignore`.

6. Run the server:
```bash
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

### Testing

Run integration tests:
```bash
chmod +x full_test.sh
./full_test.sh
```

## Application Flow

### 1. User Discovery
- User calls `GET /api/v1/influencers` to browse available AI personas
- No authentication required

### 2. Authentication
- User obtains JWT token from authentication service
- Token must contain: `user_id`, `exp`, `iss`

### 3. Start Conversation
- User calls `POST /api/v1/chat/conversations` with influencer_id
- System creates or returns existing conversation
- Enforces one conversation per user-influencer pair

### 4. Send Messages
- User sends message via `POST /conversations/{id}/messages`
- Backend flow:
  1. Validates user ownership
  2. Saves user message to database
  3. Retrieves conversation history
  4. Calls Gemini API with influencer personality + context + new message
  5. Saves AI response
  6. Returns both messages

### 5. Multimodal Messages
- For images: Upload via `/media/upload`, then include URL in message
- For audio: Upload via `/media/upload`, system transcribes and processes
- Gemini analyzes images and text together

### 6. View History
- User calls `GET /conversations/{id}/messages` for full history
- Supports pagination and ordering

### 7. Manage Conversations
- List all conversations: `GET /conversations`
- Delete conversation: `DELETE /conversations/{id}`

## Message Types

**text**: Plain text message
**multimodal**: Text with one or more images
**image**: Image only, no text
**audio**: Voice message (transcribed to text)

## API Documentation

Once running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Logging

Application logs are stored in `logs/yral_ai_chat.log`

View logs:
```bash
tail -f logs/yral_ai_chat.log
```

## Configuration

All configuration is managed via environment variables in `.env` file.

Key settings:
- `DATABASE_URL`: PostgreSQL connection string
- `JWT_SECRET_KEY`: Secret for JWT signing
- `GEMINI_API_KEY`: Google Gemini API key
- `MEDIA_UPLOAD_DIR`: Local storage directory
- `CORS_ORIGINS`: Allowed origins for CORS

## Production Deployment

1. Set `DEBUG=False` and `ENVIRONMENT=production`
2. Change `JWT_SECRET_KEY` to strong random value
3. Configure proper CORS origins
4. Use production database with SSL
5. Run with multiple workers:
```bash
uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 4
```

## Error Handling

All errors follow consistent format:
```json
{
  "error": "Error Type",
  "message": "Human-readable message",
  "details": {}
}
```

Common HTTP status codes:
- 200: Success
- 201: Created
- 400: Bad Request
- 401: Unauthorized
- 403: Forbidden
- 404: Not Found
- 413: Payload Too Large
- 429: Rate Limit Exceeded
- 500: Internal Server Error
- 503: Service Unavailable

## License

MIT

