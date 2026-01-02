"""
Yral AI Chat API - Main Application
"""
import os
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from loguru import logger
from sentry_sdk.integrations.fastapi import FastApiIntegration

from src.api.v1 import chat, health, influencers, media
from src.config import settings
from src.core.exceptions import BaseAPIException
from src.core.metrics import MetricsMiddleware, metrics_endpoint
from src.db.base import db
from src.middleware.logging import RequestLoggingMiddleware, configure_logging
from src.middleware.rate_limiter import RateLimitMiddleware
from src.middleware.versioning import APIVersionMiddleware
from src.services.gemini_client import gemini_client


# Debug function to log when Sentry captures events
def sentry_before_send(event, hint):
    """Callback to log when Sentry captures an event"""
    try:
        # Always log that we got an event
        logger.info(f"✅ Sentry before_send called - event type: {event.get('type', 'unknown')}")
        
        # Log environment tag
        tags = event.get("tags", {})
        environment = tags.get("environment", "NOT SET")
        logger.info(f"   Environment tag: {environment}")
        
        # Extract exception info if available
        exc_type = "unknown"
        if "exception" in event:
            exc = event.get("exception", {})
            values = exc.get("values", [])
            if values and len(values) > 0:
                exc_type = values[0].get("type", "unknown")
        
        message = event.get("message", "N/A")
        logger.info(f"   Exception type: {exc_type}, Message: {message}")
        
        # Log the event ID if available
        if "event_id" in event:
            logger.info(f"   Event ID: {event['event_id']}")
            
    except Exception as e:
        logger.error(f"❌ Error in sentry_before_send: {e}", exc_info=True)
    return event  # Return event to send it, or None to drop it

# Only initialize Sentry for production environment to avoid capturing staging/dev/test data
is_running_tests = os.getenv("PYTEST_CURRENT_TEST") is not None
if not is_running_tests and settings.sentry_dsn and settings.environment == "production":
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        profiles_sample_rate=settings.sentry_profiles_sample_rate,
        release=settings.sentry_release,
        # Add data like request headers and IP for users
        # See https://docs.sentry.io/platforms/python/data-management/data-collected/ for more info
        send_default_pii=True,
        integrations=[
            FastApiIntegration(transaction_style="endpoint"),
        ],
        before_send=sentry_before_send,
        # Enable debug mode to see transport logs
        debug=True,  # Keep enabled to verify events are being sent
    )
    logger.info(f"Sentry initialized for environment: {settings.sentry_environment}")
    logger.info(f"Sentry DSN configured: {settings.sentry_dsn[:30]}...")
    logger.info(f"Sentry release: {settings.sentry_release}")
    
    # Test Sentry connection with a test message
    try:
        # Set additional tags for debugging
        sentry_sdk.set_tag("deployment", "manual-test")
        
        test_event_id = sentry_sdk.capture_message("Sentry integration test - startup", level="error")
        logger.info(f"✅ Sentry test message sent: event_id={test_event_id}")
        logger.info(f"   Environment tag: {settings.sentry_environment}")
        
        # Flush with longer timeout
        if sentry_sdk.flush(timeout=5):
            logger.info("✅ Sentry events flushed successfully")
        else:
            logger.warning("⚠️  Sentry flush timed out - events may still be queued")
    except Exception as e:
        logger.warning(f"❌ Failed to send Sentry test message: {e}", exc_info=True)
elif is_running_tests:
    logger.debug("Sentry disabled during test execution")
elif settings.sentry_dsn and settings.environment != "production":
    logger.info(f"Sentry DSN configured but disabled for {settings.environment} environment (production only)")
else:
    logger.info("Sentry DSN not configured, error tracking disabled")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown
    """
    configure_logging()

    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    logger.info(f"Environment: {settings.environment}")

    await db.connect()

    logger.info("All services initialized")

    yield

    logger.info("Shutting down...")
    await db.disconnect()
    await gemini_client.close()
    logger.info("Shutdown complete")

root_path: str | None = "/staging" if settings.environment == "staging" else None

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI Chat API for Yral with multimodal support",
    lifespan=lifespan,
    root_path=root_path,  # type: ignore[arg-type]
    docs_url="/docs",
    redoc_url="/redoc",
    swagger_ui_parameters={
        "persistAuthorization": True
    },
    redoc_js_url="https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js",
    redoc_favicon_url="https://fastapi.tiangolo.com/img/favicon.png"
)

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title=settings.app_name,
        version=settings.app_version,
        description="AI Chat API for Yral with multimodal support",
        routes=app.routes,
    )
    
    if settings.environment == "staging":
        openapi_schema["servers"] = [{"url": "/staging", "description": "Staging environment"}]
    
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Enter your JWT token (without 'Bearer' prefix)"
        }
    }
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi  # type: ignore[method-assign]

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(MetricsMiddleware)
app.add_middleware(APIVersionMiddleware)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle Pydantic validation errors"""
    logger.warning(f"Validation error on {request.url.path}: {exc.errors()}")

    serialized_errors = []
    for error in exc.errors():
        serialized_error = {
            "type": error.get("type"),
            "loc": error.get("loc"),
            "msg": error.get("msg"),
            "input": error.get("input"),
        }
        
        if "ctx" in error:
            ctx = error["ctx"]
            if isinstance(ctx, dict):
                serialized_ctx = {}
                for key, value in ctx.items():
                    if isinstance(value, str | int | float | bool | type(None)):
                        serialized_ctx[key] = value
                    else:
                        serialized_ctx[key] = str(value)
                serialized_error["ctx"] = serialized_ctx
            else:
                serialized_error["ctx"] = str(ctx)
        
        if "url" in error:
            serialized_error["url"] = error["url"]
            
        serialized_errors.append(serialized_error)

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "error": "validation_error",
            "message": "Request validation failed",
            "details": {
                "errors": serialized_errors,
                "body": exc.body if settings.debug else None
            }
        }
    )


@app.exception_handler(BaseAPIException)
async def api_exception_handler(request: Request, exc: BaseAPIException):
    """Handle custom API exceptions"""
    detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
    logger.warning(
        f"{exc.error_code} on {request.url.path}: {detail.get('message', 'Unknown error')}"
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.detail
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unhandled exceptions"""
    logger.error(f"Unhandled exception on {request.url.path}: {exc}", exc_info=True)
    # Note: Sentry automatically captures exceptions via FastAPI integration,
    # so we don't need to explicitly call capture_exception here
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "internal_server_error",
            "message": str(exc) if settings.debug else "An unexpected error occurred",
            "details": {} if not settings.debug else {"exception_type": type(exc).__name__}
        }
    )


app.include_router(health.router)
app.include_router(influencers.router)
app.include_router(chat.router)
app.include_router(media.router)

@app.get("/metrics", tags=["Monitoring"])
async def get_metrics():
    """Prometheus metrics endpoint"""
    return await metrics_endpoint()

@app.get("/", tags=["Root"])
async def root():
    """Root endpoint"""
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "status": "running",
        "docs": "/docs",
        "health": "/health",
        "metrics": "/metrics"
    }

@app.get("/sentry-debug", tags=["Debug"])
async def trigger_error():
    """
    Debug endpoint to test Sentry error tracking.
    
    This endpoint intentionally triggers a division by zero error
    to verify that Sentry is capturing exceptions correctly.
    
    **Warning**: Only use this in production for initial testing,
    then consider removing or restricting access.
    """
    # Test Sentry with a unique message to verify it's working
    import sentry_sdk
    sentry_sdk.capture_message("Test message from /sentry-debug endpoint", level="error")
    
    # Also trigger an exception
    1 / 0  # noqa: B018


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug
    )


