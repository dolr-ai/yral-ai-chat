# Yral AI Chat API

A FastAPI-based REST API for multimodal AI chat with personalized influencer personas powered by Google Gemini.

## Features

- Multiple AI influencer personas with unique personalities
- Multimodal support (text, images, audio)
- Conversation history and context awareness
- JWT-based authentication
- SQLite database with async operations and Litestream replication
- S3-compatible media storage
- RESTful API design

## Tech Stack

- **Framework**: FastAPI 0.104.1
- **Database**: SQLite with aiosqlite + Litestream for real-time S3 backups
- **AI Model**: Google Gemini 2.5 Flash
- **Authentication**: JWT (PyJWT)
- **Server**: Uvicorn with async support
- **Storage**: S3-compatible object storage (Hetzner)

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
│   └── sqlite/
│       ├── 001_init_schema.sql       # SQLite schema
│       └── 002_seed_influencers.sql  # Initial data
├── scripts/
│   └── run_migrations.py         # Database migration script
├── tests/                        # Test files
├── data/                         # SQLite database storage
├── logs/                         # Application logs
├── requirements.txt              # Python dependencies
└── env.example                   # Environment variables template
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

## API Documentation

### Interactive Documentation

When the server is running, access the interactive API documentation:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### OpenAPI Specification

The complete OpenAPI specification is available in:
- `docs/api/openapi.yaml` (YAML format)
- `docs/api/openapi.json` (JSON format)

**Regenerate OpenAPI spec after API changes:**
```bash
python scripts/export_openapi_spec.py
```

This updates both YAML and JSON files with the latest API schema, including operation IDs, request/response models, and examples.

### Documentation

Comprehensive documentation is available in the `docs/` directory:
- **[API Documentation](docs/api/)** - OpenAPI specs and guides
- **[System Architecture](docs/architecture/system-design.md)** - High-level design
- **[Database Schema](docs/architecture/database.md)** - Database structure
- **[Development Guide](docs/development/development-guide.md)** - Development workflow
- **[Testing Guide](docs/development/testing-guide.md)** - Testing strategies

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

### Basic Setup

1. Set `DEBUG=False` and `ENVIRONMENT=production`
2. Change `JWT_SECRET_KEY` to strong random value
3. Configure proper CORS origins
4. Use production database with SSL
5. Run with multiple workers:
```bash
uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Reverse Proxy Setup (Nginx + HTTPS)

To route HTTPS traffic (port 443) to your FastAPI app on port 8000:

**Quick Setup:**
```bash
sudo ./scripts/setup_nginx.sh
```

**Manual Setup:**
1. Copy nginx config: `sudo cp nginx/yral-ai-chat.conf /etc/nginx/sites-available/yral-ai-chat.conf`
2. Edit the config and replace `chat.yral.com` with your actual domain
3. Enable the site: `sudo ln -s /etc/nginx/sites-available/yral-ai-chat.conf /etc/nginx/sites-enabled/`
4. Test config: `sudo nginx -t`
5. Restart nginx: `sudo systemctl restart nginx`
6. Set up SSL: `sudo certbot --nginx -d chat.yral.com -d www.chat.yral.com`

See `nginx/README.md` for detailed instructions and troubleshooting.

**After setup, update your `.env` file:**
```
CORS_ORIGINS=https://chat.yral.com,https://www.chat.yral.com
MEDIA_BASE_URL=https://chat.yral.com/media
```

### Docker Deployment

The application can be deployed using Docker and Docker Compose. This is the recommended approach for production deployments.

#### Prerequisites

- Docker 20.10+
- Docker Compose 2.0+

#### Manual Deployment

1. **Set required environment variables:**

   The following environment variables are **required**:
   - `JWT_SECRET_KEY`: Secret for JWT signing
   - `GEMINI_API_KEY`: Google Gemini API key

   Optional variables can be set as needed (see `env.example` for full list).

2. **Deploy using docker-compose:**

   ```bash
   # Set required secrets and deploy
   JWT_SECRET_KEY="your-secret-key" \
   GEMINI_API_KEY="your-gemini-api-key" \
   docker-compose up -d --build
   ```

   For multiple secrets:
   ```bash
   JWT_SECRET_KEY="secret1" \
   GEMINI_API_KEY="secret2" \
   CORS_ORIGINS="https://chat.yral.com" \
   MEDIA_BASE_URL="https://chat.yral.com/media" \
   docker-compose up -d --build
   ```

3. **Using the deployment script:**

   ```bash
   # Set environment variables
   export JWT_SECRET_KEY="your-secret-key"
   export GEMINI_API_KEY="your-gemini-api-key"
   
   # Run deployment script
   ./scripts/deploy.sh
   ```

   The script will:
   - Build the Docker image
   - Stop existing containers
   - Start new containers with health checks
   - Run database migrations if needed
   - Verify the service is healthy

4. **Check service status:**

   ```bash
   docker-compose ps
   docker-compose logs -f yral-ai-chat
   ```

5. **Stop the service:**

   ```bash
   docker-compose down
   ```

#### CI/CD Deployment

The repository includes a GitHub Actions workflow that automatically deploys on every push to the `main` branch.

**Setup GitHub Secrets:**

Configure the following secrets in your GitHub repository (Settings → Secrets and variables → Actions):

**Required:**
- `DEPLOY_HOST`: Server IP address or hostname
- `DEPLOY_USER`: SSH username for deployment
- `DEPLOY_SSH_KEY`: Private SSH key for server access
- `JWT_SECRET_KEY`: JWT signing secret
- `GEMINI_API_KEY`: Google Gemini API key

**Optional (with defaults):**
- `APP_NAME`, `APP_VERSION`, `ENVIRONMENT`, `DEBUG`
- `DATABASE_PATH`, `JWT_ALGORITHM`, `JWT_ISSUER`
- `GEMINI_MODEL`, `GEMINI_MAX_TOKENS`, `GEMINI_TEMPERATURE`
- `MEDIA_UPLOAD_DIR`, `MEDIA_BASE_URL`
- `CORS_ORIGINS`, `CORS_ALLOW_CREDENTIALS`
- `USE_S3`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_S3_BUCKET`, `AWS_REGION`, `S3_ENDPOINT`
- `USE_WHISPER`, `WHISPER_API_KEY`
- `RATE_LIMIT_PER_MINUTE`, `RATE_LIMIT_PER_HOUR`
- `LOG_LEVEL`, `LOG_FORMAT`

**How it works:**

1. On push to `main`, GitHub Actions:
   - Checks out the code
   - SSH into the deployment server
   - Pulls the latest code
   - Creates staging database if it doesn't exist
   - Builds and deploys all services (including Metabase BI dashboard) using `docker-compose` with secrets from GitHub Secrets
   - Runs health checks to verify deployment

2. Secrets are passed as environment variables to `docker-compose up -d`, ensuring they are never stored in files on the server.

**Services Deployed:**
- Production API (port 8000)
- Staging API (port 8001)
- Metabase BI Dashboard (port 3000)
- Nginx reverse proxy

#### BI Dashboard (Metabase)

The deployment includes Metabase for interactive analytics dashboards:

- **Production UI:** `https://chat.yral.com/metabase/` (container `metabase` on port 3000)
- **Staging UI:** `https://chat.yral.com/staging/metabase/` (container `metabase-staging` on port 3001)
- **Local dev:** `http://localhost:3000` (prod Metabase), `http://localhost:3001` (staging Metabase)
- **SQLite files:** `/data/yral_chat.db` (prod), `/data/yral_chat_staging.db` (staging)
- **Views for analytics (optional):** `migrations/sqlite/004_dashboard_views.sql` creates:
  - `v_user_conversation_summary` (PID, bot, last seen, time spent)
  - `v_conversation_threads` (full conversation)
  - `v_bot_performance`, `v_user_engagement`, `v_daily_activity`, `v_recent_activity`
  You can query these directly from Metabase for most dashboards.

#### Docker Volumes

The following directories are persisted as Docker volumes:
- `./data`: SQLite database files (production and staging)
- `./uploads`: Uploaded media files
- `./logs`: Application logs
- `metabase-data`: Metabase metadata (dashboards, queries, settings)

These directories are created automatically if they don't exist.

#### Database Migrations

Database migrations are handled automatically on first startup. The SQLite schema is created from `migrations/sqlite/001_init_schema.sql` if the database doesn't exist.

#### Health Checks

The Docker container includes a health check that verifies the `/health` endpoint. You can check container health with:

```bash
docker-compose ps
```

#### Troubleshooting

**View logs:**
```bash
docker-compose logs -f yral-ai-chat
```

**Restart service:**
```bash
docker-compose restart yral-ai-chat
```

**Rebuild and redeploy:**
```bash
docker-compose up -d --build
```

**Check health endpoint:**
```bash
curl http://localhost:8000/health
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

## Additional Resources:

Front End Integration Guide- https://gist.github.com/kevin-antony-yral/3089b965f30b787923c7a58577ef37f9
Message Types- https://gist.github.com/kevin-antony-yral/94360fe6923ecd7d02bf03b51c10dbf2

