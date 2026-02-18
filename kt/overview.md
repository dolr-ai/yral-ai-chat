# 1. Overview & Architecture

## Introduction

**Yral AI Chat** is a FastAPI-based REST API designed to power multimodal AI chat experiences with personalized influencer personas. It leverages Google Gemini for AI generation, allowing users to interact with AI characters via text, images, and audio.

## Key Features

* **Personalized AI Personas**: Distinct influencers with unique system instructions and personalities.
* **Multimodal Interaction**: Supports Text-to-Text, Image-to-Text (Vision), and Audio-to-Text (Transcription).
* **Real-time & Background Processing**: Async API handles immediate AI responses while background tasks manage logging, analytics, and caching.
* **Data Safety**: SQLite database with **Litestream** for real-time replication to S3, ensuring zero data loss.

## High-Level Architecture

```mermaid
graph TD
    Client[Mobile/Web Client] <-->|HTTPS/WSS| LB[Nginx Load Balancer]
    LB <-->|HTTP| API[FastAPI Server]
    
    subgraph "Application Core"
        API --> Auth[JWT Auth]
        API --> Service[Chat/Influencer Services]
        Service --> Repos[Data Repositories]
    end
    
    subgraph "External Services"
        Service -->|API| Gemini[Google Gemini AI]
        Service -->|API| OpenRouter[OpenRouter (NSFW)]
        Service -->|API| Replicate[Replicate (Img Gen)]
        Service <-->|S3 API| Storage[Object Storage (S3)]
    end
    
    subgraph "Data Layer"
        Repos --> SQLite[(SQLite DB)]
        Litestream[Litestream Sidecar] -->|Replicate| Storage
    end
```

## Tech Stack

| Component | Technology | Description |
| :--- | :--- | :--- |
| **Framework** | FastAPI | High-performance async Python web framework. |
| **Database** | SQLite + aiosqlite | Lightweight, serverless relational database. |
| **Replication** | Litestream | Real-time streaming replication to S3 for disaster recovery. |
| **AI Model** | Google Gemini 1.5 Flash | Primary LLM for chat and vision. |
| **Auth** | PyJWT | Stateless JWT authentication. |
| **Storage** | S3-compatible | Used for media uploads and database backups. |

## Project Structure

```
yral-ai-chat/
├── src/
│   ├── api/            # API Route handlers (v1, v2)
│   ├── core/           # Config, exceptions, logging
│   ├── db/             # Database connection, repositories, schemas
│   ├── services/       # Business logic (Chat, Auth, Storage, AI)
│   ├── models/         # Pydantic models (Requests, Responses, Entities)
│   └── main.py         # App entry point
├── migrations/         # SQL migration files
├── scripts/            # Utility scripts (deploy, migrate)
├── tests/              # Pytest suite
└── docker-compose.*    # Docker orchestration
```
