"""
Background task utilities for non-blocking operations
"""
from loguru import logger

from src.core.cache import cache
from src.core.metrics import ai_tokens_used_total


async def log_ai_usage(
    model: str,
    tokens: int,
    user_id: str,
    conversation_id: str
):
    """
    Background task to log AI usage metrics
    
    Args:
        model: AI model used
        tokens: Number of tokens consumed
        user_id: User identifier
        conversation_id: Conversation identifier
    """
    try:
        ai_tokens_used_total.labels(model=model).inc(tokens)

        logger.info(
            "AI usage recorded",
            extra={
                "model": model,
                "tokens": tokens,
                "user_id": user_id,
                "conversation_id": conversation_id
            }
        )
    except Exception as e:
        logger.error(f"Failed to log AI usage: {e}")


async def update_conversation_stats(conversation_id: str):
    """
    Background task to update conversation statistics
    
    Args:
        conversation_id: Conversation identifier
    """
    try:
        logger.debug(f"Updated stats for conversation: {conversation_id}")
    except Exception as e:
        logger.error(f"Failed to update conversation stats: {e}")


async def invalidate_cache_for_user(user_id: str):
    """
    Background task to invalidate user-related caches
    
    Args:
        user_id: User identifier
    """
    try:
        await cache.invalidate_pattern(f"conversations:{user_id}")
        logger.debug(f"Invalidated cache for user: {user_id}")
    except Exception as e:
        logger.error(f"Failed to invalidate cache: {e}")


async def cleanup_old_cache_entries():
    """
    Background task to clean up expired cache entries
    """
    try:
        await cache.cleanup_expired()
        stats = await cache.get_stats()

        logger.info(
            "Cache cleanup completed",
            extra=stats.model_dump()
        )
    except Exception as e:
        logger.error(f"Failed to cleanup cache: {e}")
