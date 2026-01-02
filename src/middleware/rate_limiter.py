"""
Rate limiting middleware using token bucket algorithm
"""
import time
from collections import defaultdict

from fastapi import Request, status
from fastapi.responses import JSONResponse
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware

from src.config import settings


class TokenBucket:
    """Token bucket for rate limiting"""

    def __init__(self, capacity: int, refill_rate: float):
        """
        Initialize token bucket
        
        Args:
            capacity: Maximum number of tokens
            refill_rate: Tokens added per second
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = capacity
        self.last_refill = time.time()

    def consume(self, tokens: int = 1) -> bool:
        """
        Try to consume tokens
        
        Args:
            tokens: Number of tokens to consume
            
        Returns:
            True if tokens were consumed, False if insufficient tokens
        """
        self._refill()

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    def _refill(self):
        """Refill tokens based on time elapsed"""
        now = time.time()
        elapsed = now - self.last_refill

        tokens_to_add = elapsed * self.refill_rate
        self.tokens = min(self.capacity, self.tokens + tokens_to_add)
        self.last_refill = now

    def get_retry_after(self) -> int:
        """Get seconds until next token is available"""
        if self.tokens >= 1:
            return 0
        tokens_needed = 1 - self.tokens
        return int(tokens_needed / self.refill_rate) + 1


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware with token bucket algorithm
    
    Limits requests per minute and per hour for each user/IP
    """

    def __init__(self, app):
        super().__init__(app)
        self.buckets: dict[str, tuple[TokenBucket, TokenBucket]] = defaultdict(
            lambda: (
                TokenBucket(
                    capacity=settings.rate_limit_per_minute,
                    refill_rate=settings.rate_limit_per_minute / 60.0
                ),
                TokenBucket(
                    capacity=settings.rate_limit_per_hour,
                    refill_rate=settings.rate_limit_per_hour / 3600.0
                )
            )
        )
        self.cleanup_interval = 300
        self.last_cleanup = time.time()

        self.excluded_paths = {
            "/health",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/"
        }

    async def dispatch(self, request: Request, call_next):
        """Process request with rate limiting"""

        if request.url.path in self.excluded_paths:
            return await call_next(request)

        identifier = self._get_identifier(request)

        minute_bucket, hour_bucket = self.buckets[identifier]

        if not minute_bucket.consume():
            retry_after = minute_bucket.get_retry_after()
            logger.warning(
                f"Rate limit exceeded (per minute) for {identifier} on {request.url.path}"
            )
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "rate_limit_exceeded",
                    "message": f"Too many requests. Try again in {retry_after} seconds.",
                    "retry_after": retry_after,
                    "limit_type": "per_minute",
                    "limit": settings.rate_limit_per_minute
                },
                headers={"Retry-After": str(retry_after)}
            )

        if not hour_bucket.consume():
            retry_after = hour_bucket.get_retry_after()
            logger.warning(
                f"Rate limit exceeded (per hour) for {identifier} on {request.url.path}"
            )
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "rate_limit_exceeded",
                    "message": f"Hourly rate limit exceeded. Try again in {retry_after} seconds.",
                    "retry_after": retry_after,
                    "limit_type": "per_hour",
                    "limit": settings.rate_limit_per_hour
                },
                headers={"Retry-After": str(retry_after)}
            )

        self._cleanup_buckets()

        response = await call_next(request)
        response.headers["X-RateLimit-Limit-Minute"] = str(settings.rate_limit_per_minute)
        response.headers["X-RateLimit-Limit-Hour"] = str(settings.rate_limit_per_hour)
        response.headers["X-RateLimit-Remaining-Minute"] = str(int(minute_bucket.tokens))
        response.headers["X-RateLimit-Remaining-Hour"] = str(int(hour_bucket.tokens))

        return response

    def _get_identifier(self, request: Request) -> str:
        """
        Get unique identifier for rate limiting
        
        Priority: user_id from JWT > IP address
        """
        if hasattr(request.state, "user_id"):
            return f"user:{request.state.user_id}"

        forwarded = request.headers.get("X-Forwarded-For")
        ip = forwarded.split(",")[0].strip() if forwarded else request.client.host if request.client else "unknown"

        return f"ip:{ip}"

    def _cleanup_buckets(self):
        """Remove old inactive buckets to prevent memory leak"""
        now = time.time()
        if now - self.last_cleanup < self.cleanup_interval:
            return

        inactive_threshold = now - 3600
        identifiers_to_remove = []

        for identifier, (minute_bucket, hour_bucket) in self.buckets.items():
            if (minute_bucket.last_refill < inactive_threshold and
                hour_bucket.last_refill < inactive_threshold):
                identifiers_to_remove.append(identifier)

        for identifier in identifiers_to_remove:
            del self.buckets[identifier]

        if identifiers_to_remove:
            logger.debug(f"Cleaned up {len(identifiers_to_remove)} inactive rate limit buckets")

        self.last_cleanup = now
