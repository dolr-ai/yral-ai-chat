# 4. API Architecture

## Overview

The API is built with **FastAPI** and follows RESTful principles. It supports both synchronous HTTP requests and asynchronous WebSockets.

## Authentication

* **Method**: JWT (JSON Web Token) via Bearer header.
* **Validation**: `src/auth/jwt_auth.py` validates `iss`, `exp`, and signatures.
* **Dependency**: `get_current_user` injects the authenticated user into route handlers.

## Key Endpoints

### Influencers (`/api/v1/influencers`)

* `GET /`: List all active influencers (Public).
* `GET /{id}`: Get details for a specific influencer.
* `POST /create`: Create a new custom influencer (Admin/User).

### Chat (`/api/v1/chat`)

* `POST /conversations`: Start or retrieve a conversation.
* `GET /conversations`: List user's conversations with last message preview.
* `POST /conversations/{id}/messages`: Send a message.
  * **Async**: Returns AI response immediately but uses background tasks for logging.
  * **Idempotency**: Supports `client_message_id`.
* `GET /conversations/{id}/messages`: key-based pagination for history.

### Media (`/api/v1/media`)

* `POST /upload`: Upload images/audio to S3. Returns a storage key for use in messages.

## WebSockets (`/api/v1/chat/ws`)

Used for real-time updates (e.g., new messages, typing indicators).

* **Endpoint**: `/ws/inbox/{user_id}`
* **Events**:
  * `new_message`: Pushed when a message is received (useful for multi-device sync).
  * `typing_status`: Real-time typing feedback.

## API Versioning

* Currently on **v1**.
* Routes are organized in `src/api/v1/`.
* `src/main.py` aggregates routers.
