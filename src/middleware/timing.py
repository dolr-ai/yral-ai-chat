"""
Request timing middleware for performance monitoring
"""

import time

from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware


class TimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000

        response.headers["X-Response-Time-Ms"] = f"{duration_ms:.2f}"

        logger.info(
            "request_completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 2),
                "user_agent": request.headers.get("user-agent", "unknown")[:100],
                "content_length": response.headers.get("content-length", "0"),
            },
        )

        if duration_ms > 1000:
            level = logger.warning if duration_ms < 3000 else logger.error
            level(f"SLOW REQUEST: {request.method} {request.url.path} took {duration_ms:.0f}ms")

        return response
