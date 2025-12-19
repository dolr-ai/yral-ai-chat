"""
Enhanced logging middleware with correlation IDs and structured logging
"""
import sys
import time
import uuid
from collections.abc import Callable

from fastapi import Request, Response
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for structured request/response logging with correlation IDs
    """

    def __init__(self, app):
        super().__init__(app)
        self.excluded_paths = {
            "/docs",
            "/redoc",
            "/openapi.json"
        }

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with enhanced logging"""

        # Generate correlation ID
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())

        # Add correlation ID to request state for access in route handlers
        request.state.correlation_id = correlation_id

        # Start timing
        start_time = time.time()

        # Extract request info
        method = request.method
        path = request.url.path
        query_params = dict(request.query_params) if request.query_params else None
        client_ip = self._get_client_ip(request)
        user_agent = request.headers.get("user-agent", "unknown")

        # Skip detailed logging for excluded paths
        if path not in self.excluded_paths:
            # Log incoming request
            logger.info(
                "Incoming request",
                extra={
                    "correlation_id": correlation_id,
                    "method": method,
                    "path": path,
                    "query_params": query_params,
                    "client_ip": client_ip,
                    "user_agent": user_agent[:100] if user_agent else None
                }
            )

        # Process request
        try:
            response = await call_next(request)

            # Calculate duration
            duration_ms = int((time.time() - start_time) * 1000)

            # Add correlation ID to response headers
            response.headers["X-Correlation-ID"] = correlation_id

            # Log response
            if path not in self.excluded_paths:
                log_level = "error" if response.status_code >= 500 else "warning" if response.status_code >= 400 else "info"

                log_data = {
                    "correlation_id": correlation_id,
                    "method": method,
                    "path": path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                    "client_ip": client_ip
                }

                # Add user info if available
                if hasattr(request.state, "user_id"):
                    log_data["user_id"] = request.state.user_id

                getattr(logger, log_level)(
                    f"Request completed: {method} {path} - {response.status_code} ({duration_ms}ms)",
                    extra=log_data
                )
        except Exception as e:
            # Log exception
            duration_ms = int((time.time() - start_time) * 1000)

            logger.error(
                f"Request failed: {method} {path}",
                extra={
                    "correlation_id": correlation_id,
                    "method": method,
                    "path": path,
                    "duration_ms": duration_ms,
                    "client_ip": client_ip,
                    "exception": str(e),
                    "exception_type": type(e).__name__
                }
            )
            raise
        else:
            return response

    def _get_client_ip(self, request: Request) -> str:
        """
        Get client IP address, checking for proxy headers
        
        Args:
            request: FastAPI request object
            
        Returns:
            Client IP address
        """
        # Check for forwarded IP first (behind proxy/load balancer)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # X-Forwarded-For can contain multiple IPs, get the first one
            return forwarded.split(",")[0].strip()

        # Check X-Real-IP header
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()

        # Fall back to direct client IP
        return request.client.host if request.client else "unknown"


def configure_logging():
    """
    Configure loguru logger for structured JSON logging
    """
    from src.config import settings

    # Remove default handler
    logger.remove()

    # JSON format for production
    if settings.log_format == "json":
        def json_sink(message):
            """Custom sink for JSON logging"""
            record = message.record
            log_data = {
                "timestamp": record["time"].isoformat(),
                "level": record["level"].name,
                "message": record["message"],
                "module": record["module"],
                "function": record["function"],
                "line": record["line"]
            }

            # Add extra fields
            if record["extra"]:
                log_data.update(record["extra"])

            # Add exception info if present
            if record["exception"]:
                log_data["exception"] = {
                    "type": record["exception"].type.__name__,
                    "value": str(record["exception"].value)
                }


        logger.add(
            json_sink,
            level=settings.log_level
        )
    else:
        # Human-readable format for development
        logger.add(
            sys.stdout,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
            level=settings.log_level,
            colorize=True
        )

    logger.info(f"Logging configured: level={settings.log_level}, format={settings.log_format}")
