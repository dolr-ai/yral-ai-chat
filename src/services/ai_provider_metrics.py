"""
AI Provider Usage Metrics & Analytics
Tracks usage statistics for Gemini and OpenRouter providers
"""
from datetime import datetime
from loguru import logger


class AIProviderMetrics:
    """Track and report AI provider usage metrics"""

    def __init__(self):
        """Initialize metrics tracker"""
        self.gemini_requests = 0
        self.openrouter_requests = 0
        self.gemini_errors = 0
        self.openrouter_errors = 0
        self.gemini_total_tokens = 0
        self.openrouter_total_tokens = 0
        self.start_time = datetime.now()

    def record_gemini_request(self, token_count: int = 0, error: bool = False):
        """Record a Gemini API request"""
        if error:
            self.gemini_errors += 1
            logger.warning(f"Gemini error recorded. Total Gemini errors: {self.gemini_errors}")
        else:
            self.gemini_requests += 1
            self.gemini_total_tokens += token_count
            logger.debug(
                f"Gemini request recorded. Total: {self.gemini_requests}, "
                f"Tokens: {self.gemini_total_tokens}"
            )

    def record_openrouter_request(self, token_count: int = 0, error: bool = False):
        """Record an OpenRouter API request"""
        if error:
            self.openrouter_errors += 1
            logger.warning(
                f"OpenRouter error recorded. Total OpenRouter errors: {self.openrouter_errors}"
            )
        else:
            self.openrouter_requests += 1
            self.openrouter_total_tokens += token_count
            logger.debug(
                f"OpenRouter request recorded. Total: {self.openrouter_requests}, "
                f"Tokens: {self.openrouter_total_tokens}"
            )

    def get_metrics_summary(self) -> dict:
        """Get current metrics summary"""
        total_requests = self.gemini_requests + self.openrouter_requests
        total_errors = self.gemini_errors + self.openrouter_errors
        total_tokens = self.gemini_total_tokens + self.openrouter_total_tokens
        uptime = datetime.now() - self.start_time

        return {
            "gemini": {
                "requests": self.gemini_requests,
                "errors": self.gemini_errors,
                "total_tokens": self.gemini_total_tokens,
                "error_rate": (self.gemini_errors / (self.gemini_requests + self.gemini_errors) * 100)
                if (self.gemini_requests + self.gemini_errors) > 0 else 0,
            },
            "openrouter": {
                "requests": self.openrouter_requests,
                "errors": self.openrouter_errors,
                "total_tokens": self.openrouter_total_tokens,
                "error_rate": (self.openrouter_errors / (self.openrouter_requests + self.openrouter_errors) * 100)
                if (self.openrouter_requests + self.openrouter_errors) > 0 else 0,
            },
            "total": {
                "requests": total_requests,
                "errors": total_errors,
                "tokens": total_tokens,
                "error_rate": (total_errors / (total_requests + total_errors) * 100)
                if (total_requests + total_errors) > 0 else 0,
            },
            "uptime_seconds": uptime.total_seconds(),
        }

    def get_human_readable_summary(self) -> str:
        """Get a human-readable metrics summary"""
        metrics = self.get_metrics_summary()
        summary = "\n=== AI Provider Metrics Summary ===\n"
        summary += f"Gemini:\n"
        summary += f"  Requests: {metrics['gemini']['requests']}\n"
        summary += f"  Errors: {metrics['gemini']['errors']}\n"
        summary += f"  Error Rate: {metrics['gemini']['error_rate']:.2f}%\n"
        summary += f"  Tokens: {metrics['gemini']['total_tokens']}\n"
        summary += f"\nOpenRouter:\n"
        summary += f"  Requests: {metrics['openrouter']['requests']}\n"
        summary += f"  Errors: {metrics['openrouter']['errors']}\n"
        summary += f"  Error Rate: {metrics['openrouter']['error_rate']:.2f}%\n"
        summary += f"  Tokens: {metrics['openrouter']['total_tokens']}\n"
        summary += f"\nTotal:\n"
        summary += f"  Requests: {metrics['total']['requests']}\n"
        summary += f"  Errors: {metrics['total']['errors']}\n"
        summary += f"  Error Rate: {metrics['total']['error_rate']:.2f}%\n"
        summary += f"  Tokens: {metrics['total']['tokens']}\n"
        summary += f"  Uptime: {metrics['uptime_seconds']:.0f}s\n"
        summary += "===================================\n"
        return summary

    def reset_metrics(self):
        """Reset all metrics"""
        self.gemini_requests = 0
        self.openrouter_requests = 0
        self.gemini_errors = 0
        self.openrouter_errors = 0
        self.gemini_total_tokens = 0
        self.openrouter_total_tokens = 0
        self.start_time = datetime.now()
        logger.info("All metrics reset")


# Global metrics instance
_metrics_instance: AIProviderMetrics | None = None


def get_metrics_instance() -> AIProviderMetrics:
    """Get global metrics instance (lazy singleton)"""
    global _metrics_instance
    if _metrics_instance is None:
        _metrics_instance = AIProviderMetrics()
    return _metrics_instance


def record_api_request(provider: str, token_count: int = 0, error: bool = False):
    """Record an API request to the global metrics instance"""
    metrics = get_metrics_instance()
    if provider.lower() == "gemini":
        metrics.record_gemini_request(token_count, error)
    elif provider.lower() == "openrouter":
        metrics.record_openrouter_request(token_count, error)
    else:
        logger.warning(f"Unknown provider: {provider}")
