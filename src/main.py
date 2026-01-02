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

# Import routers
from src.api.v1 import chat, health, influencers, media
from src.config import settings

# Import for error handling
from src.core.exceptions import BaseAPIException

# Import metrics
from src.core.metrics import MetricsMiddleware, metrics_endpoint
from src.db.base import db
from src.middleware.logging import RequestLoggingMiddleware

# Import middleware
from src.middleware.rate_limiter import RateLimitMiddleware
from src.middleware.versioning import APIVersionMiddleware
from src.services.gemini_client import gemini_client

# Initialize Sentry SDK for error tracking and performance monitoring
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
    )
    logger.info(f"Sentry initialized for environment: {settings.sentry_environment}")
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
    # Configure logging first
    from src.middleware.logging import configure_logging
    configure_logging()

    # Startup
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    logger.info(f"Environment: {settings.environment}")

    # Connect to database
    await db.connect()

    # Initialize services (Gemini is already initialized)
    logger.info("All services initialized")

    yield

    # Shutdown
    logger.info("Shutting down...")
    await db.disconnect()
    await gemini_client.close()
    logger.info("Shutdown complete")


# Create FastAPI app
# Set root_path for staging to help Swagger UI generate correct URLs
# This doesn't affect route matching (nginx strips the prefix), but helps with URL generation
root_path = "/staging" if settings.environment == "staging" else None

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI Chat API for Yral with multimodal support",
    lifespan=lifespan,
    root_path=root_path,
    docs_url="/docs",
    redoc_url="/redoc",
    swagger_ui_parameters={
        "persistAuthorization": True
    },
    redoc_js_url="https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js",
    redoc_favicon_url="https://fastapi.tiangolo.com/img/favicon.png"
)

# Add security scheme for Swagger UI
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title=settings.app_name,
        version=settings.app_version,
        description="AI Chat API for Yral with multimodal support",
        routes=app.routes,
    )
    
    # Set server URL based on environment for correct Swagger UI routing
    # root_path is already set above, but we also set servers for explicit Swagger UI configuration
    if settings.environment == "staging":
        openapi_schema["servers"] = [{"url": "/staging", "description": "Staging environment"}]
    # Production: Don't set servers array - let Swagger UI use default (current origin)
    
    # Add JWT Bearer authentication
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

app.openapi = custom_openapi


# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting middleware

app.add_middleware(RateLimitMiddleware)

# Enhanced request logging middleware

app.add_middleware(RequestLoggingMiddleware)

# Metrics collection middleware

app.add_middleware(MetricsMiddleware)

# API versioning middleware

app.add_middleware(APIVersionMiddleware)


# Error handling



@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle Pydantic validation errors"""
    logger.warning(f"Validation error on {request.url.path}: {exc.errors()}")

    # Manually serialize errors to handle non-JSON-serializable objects like ValueError
    serialized_errors = []
    for error in exc.errors():
        serialized_error = {
            "type": error.get("type"),
            "loc": error.get("loc"),
            "msg": error.get("msg"),
            "input": error.get("input"),
        }
        
        # Handle ctx field which may contain non-serializable objects
        if "ctx" in error:
            ctx = error["ctx"]
            if isinstance(ctx, dict):
                serialized_ctx = {}
                for key, value in ctx.items():
                    # Convert non-primitive types to strings
                    if isinstance(value, (str, int, float, bool, type(None))):
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
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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
    logger.warning(
        f"{exc.error_code} on {request.url.path}: {exc.detail.get('message')}"
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.detail
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unhandled exceptions"""
    logger.error(f"Unhandled exception on {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "internal_server_error",
            "message": str(exc) if settings.debug else "An unexpected error occurred",
            "details": {} if not settings.debug else {"exception_type": type(exc).__name__}
        }
    )


# Media files are served directly from S3 - no local mount needed


# Register routers
app.include_router(health.router)
app.include_router(influencers.router)
app.include_router(chat.router)
app.include_router(media.router)


# Metrics endpoint


@app.get("/metrics", tags=["Monitoring"])
async def get_metrics():
    """Prometheus metrics endpoint"""
    return await metrics_endpoint()


# Root endpoint
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


# Sentry debug endpoint (for testing Sentry integration)
@app.get("/sentry-debug", tags=["Debug"])
async def trigger_error():
    """
    Debug endpoint to test Sentry error tracking.
    
    This endpoint intentionally triggers a division by zero error
    to verify that Sentry is capturing exceptions correctly.
    
    **Warning**: Only use this in production for initial testing,
    then consider removing or restricting access.
    """
    # Intentionally trigger division by zero to test Sentry error capture
    raise ZeroDivisionError("Intentional error for Sentry testing")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug
    )


