# 5. Core Logic

## ChatService (`src/services/chat_service.py`)

The heart of the application, managing the conversation flow.

### Key Workflows

#### 1. Creating a Conversation

* Checks if a conversation already exists for the User + Influencer pair.
* If new, creates a record in `conversations` and optionally inserts a greeting message defined in `ai_influencers`.

#### 2. Sending a Message

* **Validation**: Verifies user ownership and influencer status.
* **Deduplication**: Checks `client_message_id` to prevent double-processing.
* **User Message**: Saved to DB (transcribed if audio).
* **Context Building**: Fetches recent history (last 10 messages) + System Instructions.
* **AI Generation**: Calls `Gemini` (or `OpenRouter` for NSFW).
* **Broadcasting**: Sends "typing" status via WebSocket.
* **Response**: AI response saved to DB and returned to user.
* **Async Tasks**: Background tasks trigger `log_ai_usage` and cache invalidation.

## AI Integration

### Gemini Client (`src/services/gemini_client.py`)

* Uses Google's `genai` SDK.
* **Retry Logic**: Exponential backoff using `tenacity` for resilience.
* **Vision**: Handles image inputs by sending media URLs to Gemini.
* **Audio**: Can transcribe audio files via Gemini API.

### OpenRouter Client (`src/services/openrouter_client.py`)

* Fallback/Alternative provider (e.g., for NSFW content).
* Standard OpenAI-compatible API interface.

## Background Tasks

Defined in `src/core/background_tasks.py`. handled by FastAPI's `BackgroundTasks`.

* **Usage Logging**: Records token usage for analytics.
* **Cache Invalidation**: Clears Redis/memory cache after updates.
* **Stats Update**: Recalculates message counts.

## Caching

* **Strategy**: Read-heavy endpoints (like list influencers) are cached.
* **Invalidation**: Write operations (sending messages) trigger invalidation of relevant keys.
