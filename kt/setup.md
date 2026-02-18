# 2. Setup & Deployment

## Prerequisites

* **Python**: 3.12+
* **Docker**: 20.10+ (for containerized deployment)
* **API Keys**: Google Gemini API Key
* **Environment**: `.env` file configured (see `env.example`)

## Local Development

1. **Clone & Environment**

    ```bash
    git clone <repo_url>
    cd yral-ai-chat
    python -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    ```

2. **Configuration**
    Copy `.env.example` to `.env` and set `GEMINI_API_KEY` and `JWT_SECRET_KEY`.

3. **Database Setup**
    The app uses SQLite. Migrations run automatically on startup in Docker, but locally you can init:

    ```bash
    # Run migrations using the included script
    python scripts/run_migrations.py
    ```

4. **Run Server**

    ```bash
    uvicorn src.main:app --reload --port 8000
    ```

## Docker Deployment (Production)

The application is containerized and managed via `docker-compose`.

### Files

* `Dockerfile`: Multi-stage Python build.
* `docker-compose.prod.yml`: Production orchestration (App + Nginx + Watchtower).
* `docker-compose.staging.yml`: Staging environment.

### Deployment Commands

```bash
# Production
docker compose -f docker-compose.prod.yml up -d --build

# Staging
docker compose -f docker-compose.staging.yml up -d --build
```

## Continuous Deployment (CI/CD)

A **GitHub Actions** workflow (`deploy.yml`) handles deployment:

1. Triggers on push to `main`.
2. SSHs into the deployment server.
3. Pulls latest code.
4. Rebuilds and restarts containers using `docker compose`.
5. **Zero-Downtime**: Not fully guaranteed with SQLite unless using Blue/Green, but Litestream mitigates data risk.

## Data Replication (Litestream)

**Critical**: This app uses **Litestream** to replicate the SQLite database to S3 in real-time.

* **Process**: Litestream runs as a subprocess in the Docker container.
* **Backup**: Pushes WAL frames to S3 every few seconds.
* **Restore**: On container startup, Litestream checks if the DB exists. If not, it restores from S3 automatically.
* **Config**: Controlled by `LITESTREAM_BUCKET`, `LITESTREAM_ACCESS_KEY_ID`, etc., in `.env`.
