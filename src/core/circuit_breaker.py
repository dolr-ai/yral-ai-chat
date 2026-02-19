"""
Circuit breaker pattern implementation for external service calls
"""

import time
from collections.abc import Callable
from enum import Enum

from loguru import logger

from src.models.internal import CircuitBreakerState


class CircuitState(Enum):
    """Circuit breaker states"""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failures detected, rejecting calls
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open and rejecting calls"""


class CircuitBreaker:
    """
    Circuit breaker for protecting against cascading failures
    """

    def __init__(self, failure_threshold: int = 5, timeout: int = 60, recovery_timeout: int = 30):
        """
        Initialize circuit breaker

        Args:
            failure_threshold: Number of failures before opening circuit
            timeout: Seconds to wait before attempting recovery
            recovery_timeout: Timeout for recovery test calls
        """
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.recovery_timeout = recovery_timeout

        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitState.CLOSED

    def call(self, func: Callable, *args, **kwargs) -> object:
        """
        Execute function with circuit breaker protection

        Args:
            func: Function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Function result

        Raises:
            CircuitBreakerOpenError: If circuit is open
            Exception: If function fails
        """
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
                logger.info("Circuit breaker entering HALF_OPEN state")
            else:
                raise CircuitBreakerOpenError("Circuit breaker is OPEN")

        try:
            result = func(*args, **kwargs)
        except Exception:
            self._on_failure()
            raise
        else:
            self._on_success()
            return result

    async def call_async(self, func: Callable, *args, **kwargs) -> object:
        """
        Execute async function with circuit breaker protection

        Args:
            func: Async function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Function result

        Raises:
            CircuitBreakerOpenError: If circuit is open
            Exception: If function fails
        """
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
                logger.info("Circuit breaker entering HALF_OPEN state")
            else:
                raise CircuitBreakerOpenError("Circuit breaker is OPEN")

        try:
            result = await func(*args, **kwargs)
        except Exception:
            self._on_failure()
            raise
        else:
            self._on_success()
            return result

    def _on_success(self):
        """Handle successful call"""
        if self.state == CircuitState.HALF_OPEN:
            logger.info("Circuit breaker entering CLOSED state (recovered)")
            self.state = CircuitState.CLOSED

        self.failure_count = 0

    def _on_failure(self):
        """Handle failed call"""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.failure_threshold and self.state != CircuitState.OPEN:
            logger.warning(f"Circuit breaker entering OPEN state " f"(failures: {self.failure_count})")
            self.state = CircuitState.OPEN

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt recovery"""
        if self.last_failure_time is None:
            return True

        return (time.time() - self.last_failure_time) >= self.timeout

    def get_state(self) -> CircuitBreakerState:
        """Get current circuit breaker state"""
        return CircuitBreakerState(
            state=self.state.value, failure_count=self.failure_count, last_failure_time=self.last_failure_time
        )


gemini_circuit_breaker = CircuitBreaker(failure_threshold=3, timeout=60, recovery_timeout=30)

s3_circuit_breaker = CircuitBreaker(failure_threshold=5, timeout=30, recovery_timeout=15)
