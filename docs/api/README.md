# API Documentation

This directory contains the OpenAPI specification for the Yral AI Chat API.

## Files

- **`openapi.yaml`** - OpenAPI 3.x specification in YAML format
- **`openapi.json`** - OpenAPI 3.x specification in JSON format

## Viewing the API Documentation

### Online (Interactive)

The API documentation is automatically available when the server is running:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Local (Static)

You can view the OpenAPI spec using various tools:

1. **Swagger Editor** (online): https://editor.swagger.io/
   - Copy the contents of `openapi.yaml` or upload the file

2. **Redoc CLI** (local):
   ```bash
   npx @redocly/cli preview-docs docs/api/openapi.yaml
   ```

3. **VS Code Extension**:
   - Install "OpenAPI (Swagger) Editor" extension
   - Open `openapi.yaml` in VS Code

## Regenerating the Specification

To regenerate the OpenAPI spec after making changes to the API:

```bash
# Activate virtual environment
source venv/bin/activate

# Run export script
python scripts/export_openapi_spec.py
```

This will update both `openapi.yaml` and `openapi.json` files.

## API Overview

### Base URL

- **Development**: `http://localhost:8000`
- **Production**: `https://chat.yral.com`

### Authentication

Most endpoints require JWT authentication via Bearer token:

```
Authorization: Bearer <your_jwt_token>
```

### Key Endpoints

#### Influencers
- `GET /api/v1/influencers` - List all AI influencers
- `GET /api/v1/influencers/{id}` - Get influencer details

#### Conversations
- `POST /api/v1/chat/conversations` - Create conversation
- `GET /api/v1/chat/conversations` - List user's conversations
- `DELETE /api/v1/chat/conversations/{id}` - Delete conversation

#### Messages
- `GET /api/v1/chat/conversations/{id}/messages` - Get message history
- `POST /api/v1/chat/conversations/{id}/messages` - Send message

#### Media
- `POST /api/v1/media/upload` - Upload image or audio file

#### Health
- `GET /health` - Health check
- `GET /status` - System status

## Response Codes

- **200** - Success
- **201** - Created
- **400** - Bad Request
- **401** - Unauthorized
- **403** - Forbidden
- **404** - Not Found
- **422** - Validation Error
- **429** - Rate Limit Exceeded
- **500** - Internal Server Error
- **503** - Service Unavailable

## Rate Limits

- **Per Minute**: 60 requests
- **Per Hour**: 1000 requests

Rate limit headers are included in responses:
- `X-RateLimit-Remaining-Minute`
- `X-RateLimit-Remaining-Hour`

## Support

For API support or questions:
- Check the interactive docs at `/docs`
- Review `API_CONTRACT.md` in the root directory
- See `README.md` for setup instructions
