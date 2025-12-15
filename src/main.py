"""
Yral AI Chat API - Main Application
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from loguru import logger

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
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI Chat API for Yral with multimodal support",
    lifespan=lifespan,
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug
    )


