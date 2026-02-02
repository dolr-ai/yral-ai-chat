"""
Yral AI Chat API - Main Application
"""

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import sentry_sdk
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from loguru import logger
from sentry_sdk.integrations.fastapi import FastApiIntegration

from src.api.v1 import chat, health, influencers, media, sentry
from src.config import settings
from src.core.dependencies import (
    get_conversation_repository,
    get_influencer_repository,
    get_message_repository,
    get_storage_service,
)
from src.core.exceptions import BaseAPIException
from src.core.metrics import MetricsMiddleware, metrics_endpoint
from src.db.base import DatabaseConnectionPoolTimeoutError, db
from src.middleware.logging import RequestLoggingMiddleware, configure_logging
from src.middleware.timing import TimingMiddleware
from src.middleware.versioning import APIVersionMiddleware
from src.services.gemini_client import GeminiClient
from src.services.openrouter_client import OpenRouterClient

# --- Configuration & Monitoring ---

# Environment detection
is_test = (
    os.getenv("PYTEST_CURRENT_TEST") is not None or
    "pytest" in sys.modules or
    Path(sys.argv[0]).name.startswith("pytest")
)

# Sentry initialization
sentry_env = settings.environment if settings.environment in ("production", "staging") else None
if not is_test and settings.sentry_dsn and sentry_env:
    try:
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=sentry_env,
            traces_sample_rate=settings.sentry_traces_sample_rate,
            profiles_sample_rate=settings.sentry_profiles_sample_rate,
            release=settings.sentry_release,
            send_default_pii=True,
            integrations=[FastApiIntegration(transaction_style="endpoint")],
            debug=settings.debug,
        )
        logger.info(f"Sentry initialized for {sentry_env}")
    except Exception as e:
        logger.error(f"Failed to initialize Sentry: {e}")


# --- Lifecycle Management ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handles startup and shutdown events"""
    configure_logging()
    
    logger.info(f"Starting {settings.app_name} v{settings.app_version} ({settings.environment})")
    logger.info(f"Config: DB={settings.database_path}, Pool={settings.database_pool_size}, Sentry={'ON' if settings.sentry_dsn else 'OFF'}")

    # Initialize connections
    await db.connect()
    
    # Pre-warm repositories & AI clients
    get_conversation_repository()
    get_influencer_repository()
    get_message_repository()
    get_storage_service()
    
    app.state.gemini_client = GeminiClient()
    app.state.openrouter_client = OpenRouterClient()
    
    logger.info("Services initialized and warmed up")
    yield

    logger.info("Shutting down...")
    await db.disconnect()
    logger.info("Shutdown complete")


# --- App Initialization ---

tags_metadata = [
    {
        "name": "Chat",
        "description": "Operations with chat. Includes **WebSocket** support at `/api/v1/chat/ws/inbox/{user_id}`.",
    },
    {
        "name": "Documentation",
        "description": "Schemas and documentation for asynchronous event-driven features like WebSockets.",
    },
]

root_path = "/staging" if settings.environment == "staging" else None

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="""
AI Chat API for Yral.

### WebSocket Connection
Clients should connect to listen for real-time inbox updates:
- **URL**: `ws://{host}/api/v1/chat/ws/inbox/{user_id}`
- **Events**: See schemas in the **Documentation** section below.
""",
    lifespan=lifespan,
    root_path=root_path,
    openapi_tags=tags_metadata,
    docs_url="/docs",
    redoc_url="/redoc",
    swagger_ui_parameters={"persistAuthorization": True},
    redoc_js_url="https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js",
    redoc_favicon_url="https://fastapi.tiangolo.com/img/favicon.png",
)

# Customize OpenAPI Schema
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    schema = get_openapi(
        title=settings.app_name,
        version=settings.app_version,
        description=app.description,
        routes=app.routes,
    )

    if settings.environment == "staging":
        schema["servers"] = [{"url": "/staging", "description": "Staging environment"}]
    
    schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Enter your JWT token (without 'Bearer' prefix)",
        }
    }
    app.openapi_schema = schema
    return schema

app.openapi = custom_openapi  # type: ignore


# --- Middleware ---

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Stack order details: Timing (outermost) -> Versioning (innermost)
app.add_middleware(TimingMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(MetricsMiddleware)
app.add_middleware(APIVersionMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1000)


# --- Exception Handlers ---


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle Pydantic validation errors"""
    logger.warning(f"Validation error on {request.url.path}: {exc.errors()}")
    
    # Pydantic v2 errors contain non-serializable objects (like ValueError) in 'ctx'
    # We must sanitize them before sending to JSONResponse
    def sanitize(obj):
        if isinstance(obj, list):
            return [sanitize(i) for i in obj]
        if isinstance(obj, dict):
            return {k: sanitize(v) for k, v in obj.items()}
        if isinstance(obj, str | int | float | bool | type(None)):
            return obj
        return str(obj)

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "validation_error",
            "message": "Request validation failed",
            "details": {"errors": sanitize(exc.errors())}
        }
    )

@app.exception_handler(DatabaseConnectionPoolTimeoutError)
async def database_timeout_handler(request: Request, exc: DatabaseConnectionPoolTimeoutError):
    """Handle database connection pool timeouts"""
    logger.error(f"Database timeout on {request.url.path}")
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"error": "service_unavailable", "message": "Database busy. Try again soon."},
        headers={"Retry-After": "5"}
    )

@app.exception_handler(BaseAPIException)
async def api_exception_handler(request: Request, exc: BaseAPIException):
    """Handle domain-specific API exceptions"""
    return JSONResponse(status_code=exc.status_code, content=exc.detail, headers=exc.headers)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all for unhandled exceptions"""
    logger.error(f"Unhandled exception on {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "internal_server_error",
            "message": str(exc) if settings.debug else "An unexpected error occurred"
        }
    )


# --- Routes ---

app.include_router(health.router)
app.include_router(influencers.router)
app.include_router(chat.router)
app.include_router(media.router)
app.include_router(sentry.router, prefix="/v1")


@app.get("/metrics", tags=["Monitoring"])
async def get_metrics():
    """Prometheus metrics endpoint"""
    return await metrics_endpoint()


@app.get("/", tags=["Root"])
async def root():
    """Service information root"""
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "status": "running",
        "docs": "/docs",
        "health": "/health",
        "metrics": "/metrics",
    }


# --- Execution ---

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host=settings.host, port=settings.port, reload=settings.debug)
