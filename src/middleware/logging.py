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

from src.config import settings


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

        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())

        request.state.correlation_id = correlation_id

        start_time = time.time()

        method = request.method
        path = request.url.path
        query_params = dict(request.query_params) if request.query_params else None
        client_ip = self._get_client_ip(request)
        user_agent = request.headers.get("user-agent", "unknown")

        if path not in self.excluded_paths:
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

        try:
            response = await call_next(request)

            duration_ms = int((time.time() - start_time) * 1000)

            response.headers["X-Correlation-ID"] = correlation_id

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

                if hasattr(request.state, "user_id"):
                    log_data["user_id"] = request.state.user_id

                getattr(logger, log_level)(
                    f"Request completed: {method} {path} - {response.status_code} ({duration_ms}ms)",
                    extra=log_data
                )
        except Exception as e:
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
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()

        return request.client.host if request.client else "unknown"


def configure_logging():
    """
    Configure loguru logger for structured JSON logging
    """
    logger.remove()

    if settings.log_format == "json":
        def json_sink(message):
            """Custom sink for JSON logging"""
            # Handle both record objects and dicts (dicts occur with multiple workers)
            if isinstance(message, dict):
                record_dict = message
            else:
                record = message.record
                # Convert record to dict for consistent handling
                record_dict = {
                    "time": record.time,
                    "level": record.level,
                    "message": record.message,
                    "module": record.module,
                    "function": record.function,
                    "line": record.line,
                    "extra": record.extra or {},
                    "exception": record.exception
                }
            
            # Extract values from dict
            timestamp = record_dict.get("time")
            level = record_dict.get("level")
            log_data = {
                "timestamp": timestamp.isoformat() if hasattr(timestamp, "isoformat") else str(timestamp),
                "level": level.name if hasattr(level, "name") else str(level),
                "message": record_dict.get("message", ""),
                "module": record_dict.get("module", ""),
                "function": record_dict.get("function", ""),
                "line": record_dict.get("line", 0)
            }

            # Handle extra data (may be nested)
            extra = record_dict.get("extra", {})
            if extra:
                # If extra contains nested 'extra', unwrap it
                if isinstance(extra, dict) and "extra" in extra:
                    log_data.update(extra["extra"])
                else:
                    log_data.update(extra)

            # Handle exception
            exception = record_dict.get("exception")
            if exception:
                if hasattr(exception, "type") and hasattr(exception, "value"):
                    log_data["exception"] = {
                        "type": exception.type.__name__,
                        "value": str(exception.value)
                    }
                elif isinstance(exception, dict):
                    log_data["exception"] = exception
            
            # Write JSON log line to stdout (will be captured by container logs)
            import json
            print(json.dumps(log_data), flush=True)

        logger.add(
            json_sink,
            level=settings.log_level
        )
    else:
        logger.add(
            sys.stdout,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
            level=settings.log_level,
            colorize=True
        )

    logger.info(f"Logging configured: level={settings.log_level}, format={settings.log_format}")
