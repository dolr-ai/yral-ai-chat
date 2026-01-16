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
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from loguru import logger
from sentry_sdk.integrations.fastapi import FastApiIntegration

from src.api.v1 import chat, health, influencers, media, sentry
from src.config import settings
from src.core.exceptions import BaseAPIException, ServiceUnavailableException
from src.core.metrics import MetricsMiddleware, metrics_endpoint
from src.db.base import DatabaseConnectionPoolTimeoutError, db
from src.middleware.logging import RequestLoggingMiddleware, configure_logging
from src.middleware.versioning import APIVersionMiddleware

# Improved detection for various test environments
is_running_tests = (
    os.getenv("PYTEST_CURRENT_TEST") is not None or
    "pytest" in sys.modules or
    Path(sys.argv[0]).name.startswith("pytest")
)
# Use ENVIRONMENT variable directly for Sentry environment tagging
sentry_env = settings.environment if settings.environment in ("production", "staging") else None

# Sentry is disabled during pytest runs (is_running_tests=True) and development environments
if not is_running_tests and settings.sentry_dsn and sentry_env:
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
        logger.warning("Application will continue without Sentry error tracking")


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
    # GeminiClient instances and HTTP clients are cleaned up automatically
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


@app.exception_handler(DatabaseConnectionPoolTimeoutError)
async def database_timeout_exception_handler(request: Request, exc: DatabaseConnectionPoolTimeoutError):
    """Handle database connection pool timeouts with 503 Service Unavailable"""
    logger.error(f"Database timeout on {request.url.path}: {exc}")
    raise ServiceUnavailableException(
        message="The server is currently busy and could not connect to the database. Please try again in a few seconds.",
        headers={"Retry-After": "5"}
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
        content=exc.detail,
        headers=exc.headers
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


