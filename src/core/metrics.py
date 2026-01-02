"""
Prometheus metrics for monitoring
"""
import re
import time

from fastapi import Request
from fastapi.responses import Response as FastAPIResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware

http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"]
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
)

http_requests_in_progress = Gauge(
    "http_requests_in_progress",
    "HTTP requests currently in progress",
    ["method", "endpoint"]
)

db_query_duration_seconds = Histogram(
    "db_query_duration_seconds",
    "Database query duration in seconds",
    ["operation"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0)
)

db_connections_active = Gauge(
    "db_connections_active",
    "Number of active database connections"
)

cache_hits_total = Counter(
    "cache_hits_total",
    "Total cache hits",
    ["cache_key_prefix"]
)

cache_misses_total = Counter(
    "cache_misses_total",
    "Total cache misses",
    ["cache_key_prefix"]
)

ai_requests_total = Counter(
    "ai_requests_total",
    "Total AI service requests",
    ["service", "status"]
)

ai_request_duration_seconds = Histogram(
    "ai_request_duration_seconds",
    "AI service request duration in seconds",
    ["service"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0)
)

ai_tokens_used_total = Counter(
    "ai_tokens_used_total",
    "Total AI tokens consumed",
    ["model"]
)

rate_limit_exceeded_total = Counter(
    "rate_limit_exceeded_total",
    "Total rate limit violations",
    ["limit_type", "identifier_type"]
)


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware to collect HTTP metrics"""

    def __init__(self, app):
        super().__init__(app)
        self.excluded_paths = {"/metrics", "/health", "/docs", "/redoc", "/openapi.json"}

    async def dispatch(self, request: Request, call_next):
        """Collect metrics for each request"""

        if request.url.path in self.excluded_paths:
            return await call_next(request)

        method = request.method
        endpoint = request.url.path

        endpoint = self._normalize_endpoint(endpoint)

        http_requests_in_progress.labels(method=method, endpoint=endpoint).inc()

        start_time = time.time()

        try:
            response = await call_next(request)
            status_code = response.status_code

            duration = time.time() - start_time
            http_request_duration_seconds.labels(
                method=method,
                endpoint=endpoint
            ).observe(duration)

            http_requests_total.labels(
                method=method,
                endpoint=endpoint,
                status_code=status_code
            ).inc()

            return response

        finally:
            http_requests_in_progress.labels(method=method, endpoint=endpoint).dec()

    def _normalize_endpoint(self, path: str) -> str:
        """
        Normalize endpoint path to reduce cardinality
        Replace UUIDs and numeric IDs with placeholders
        """
        path = re.sub(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            "{uuid}",
            path,
            flags=re.IGNORECASE
        )

        return re.sub(r"/\d+", "/{id}", path)



async def metrics_endpoint():
    """Endpoint to expose Prometheus metrics"""
    return FastAPIResponse(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )
