"""
AI Provider Usage Metrics & Analytics
Tracks usage statistics for Gemini and OpenRouter providers
"""

from datetime import UTC, datetime
from functools import lru_cache

from loguru import logger


class AIProviderMetrics:
    """Track and report AI provider usage metrics"""

    def __init__(self):
        """Initialize metrics tracker"""
        self.metrics = {}  # dict of provider_name -> {requests, errors, total_tokens}
        self.start_time = datetime.now(UTC)

    def _ensure_provider(self, provider: str):
        """Initialize metrics for a provider if not exists"""
        provider = provider.lower()
        if provider not in self.metrics:
            self.metrics[provider] = {"requests": 0, "errors": 0, "total_tokens": 0}

    def record_request(self, provider: str, token_count: int = 0, error: bool = False):
        """Record an AI provider API request"""
        provider = provider.lower()
        self._ensure_provider(provider)

        if error:
            self.metrics[provider]["errors"] += 1
            logger.warning(f"{provider.capitalize()} error recorded. Total: {self.metrics[provider]['errors']}")
        else:
            self.metrics[provider]["requests"] += 1
            self.metrics[provider]["total_tokens"] += token_count
            logger.debug(
                f"{provider.capitalize()} request recorded. Total: {self.metrics[provider]['requests']}, "
                f"Tokens: {self.metrics[provider]['total_tokens']}"
            )

    def get_metrics_summary(self) -> dict:
        """Get current metrics summary"""
        total_requests = sum(m["requests"] for m in self.metrics.values())
        total_errors = sum(m["errors"] for m in self.metrics.values())
        total_tokens = sum(m["total_tokens"] for m in self.metrics.values())
        uptime = datetime.now(UTC) - self.start_time

        summary = {
            "providers": {},
            "total": {
                "requests": total_requests,
                "errors": total_errors,
                "tokens": total_tokens,
                "error_rate": (total_errors / (total_requests + total_errors) * 100)
                if (total_requests + total_errors) > 0
                else 0,
            },
            "uptime_seconds": uptime.total_seconds(),
        }

        for provider, m in self.metrics.items():
            summary["providers"][provider] = {
                "requests": m["requests"],
                "errors": m["errors"],
                "total_tokens": m["total_tokens"],
                "error_rate": (m["errors"] / (m["requests"] + m["errors"]) * 100)
                if (m["requests"] + m["errors"]) > 0
                else 0,
            }

        return summary

    def get_human_readable_summary(self) -> str:
        """Get a human-readable metrics summary"""
        metrics = self.get_metrics_summary()
        summary = "\n=== AI Provider Metrics Summary ===\n"

        for provider, m in metrics["providers"].items():
            summary += f"{provider.capitalize()}:\n"
            summary += f"  Requests: {m['requests']}\n"
            summary += f"  Errors: {m['errors']}\n"
            summary += f"  Error Rate: {m['error_rate']:.2f}%\n"
            summary += f"  Tokens: {m['total_tokens']}\n"
            summary += "\n"

        summary += "Total:\n"
        summary += f"  Requests: {metrics['total']['requests']}\n"
        summary += f"  Errors: {metrics['total']['errors']}\n"
        summary += f"  Error Rate: {metrics['total']['error_rate']:.2f}%\n"
        summary += f"  Tokens: {metrics['total']['tokens']}\n"
        summary += f"  Uptime: {metrics['uptime_seconds']:.0f}s\n"
        summary += "===================================\n"
        return summary

    def reset_metrics(self):
        """Reset all metrics"""
        self.metrics = {}
        self.start_time = datetime.now(UTC)
        logger.info("All metrics reset")


@lru_cache(maxsize=1)
def get_metrics_instance() -> AIProviderMetrics:
    """Get global metrics instance (lazy singleton)"""
    return AIProviderMetrics()


def record_api_request(provider: str, token_count: int = 0, error: bool = False):
    """Record an API request to the global metrics instance"""
    metrics = get_metrics_instance()
    metrics.record_request(provider, token_count, error)
