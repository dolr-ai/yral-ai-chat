"""
Health check and status endpoints
"""
import time
from datetime import UTC, datetime

from fastapi import APIRouter
from loguru import logger

from src.config import settings
from src.core.circuit_breaker import gemini_circuit_breaker, s3_circuit_breaker
from src.core.dependencies import InfluencerRepositoryDep, MessageRepositoryDep
from src.db.base import db
from src.models.responses import (
    DatabaseStats,
    HealthResponse,
    ServiceHealth,
    StatusResponse,
    SystemStatistics,
)

router = APIRouter(tags=["Health"])

app_start_time = time.time()


@router.get(
    "/health",
    response_model=HealthResponse,
    operation_id="healthCheck",
    summary="Health check",
    description="Fast, lightweight health check. Checks database connectivity and circuit breaker states (no external API calls)",
    responses={
        200: {"description": "Health check completed"},
        500: {"description": "Internal server error"}
    }
)
async def health_check():
    """
    Health check endpoint - fast and cost-effective
    
    This endpoint is designed to be fast and cheap. It only checks:
    - Database connectivity (local check)
    - Circuit breaker states (in-memory state, no external calls)
    
    We intentionally do NOT ping external APIs (Gemini, S3) to avoid:
    - Slow response times
    - API costs accumulating from frequent health checks
    - Rate limiting issues
    
    Circuit breaker states provide sufficient indication of service availability
    based on recent request patterns.
    """
    services = {}

    try:
        db_health = await db.health_check()
        services["database"] = ServiceHealth(
            status=db_health.status,
            latency_ms=db_health.latency_ms,
            error=db_health.error,
            pool_size=db_health.pool_size
        )
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        services["database"] = ServiceHealth(
            status="down",
            error=str(e)
        )

    # Check circuit breaker state only (fast, in-memory check - no API call)
    # This avoids costs and latency from pinging external services
    gemini_circuit_state = gemini_circuit_breaker.get_state()
    services["gemini_api"] = ServiceHealth(
        status="up" if gemini_circuit_state.state == "closed" else "degraded",
        error=None if gemini_circuit_state.state == "closed" else f"Circuit breaker {gemini_circuit_state.state}"
    )

    s3_circuit_state = s3_circuit_breaker.get_state()
    services["s3_storage"] = ServiceHealth(
        status="up" if s3_circuit_state.state == "closed" else "degraded",
        error=None if s3_circuit_state.state == "closed" else f"Circuit breaker {s3_circuit_state.state}"
    )

    overall_status = "healthy"
    degraded_count = sum(1 for s in services.values() if s.status in ["down", "degraded"])

    if any(s.status == "down" for s in services.values()):
        overall_status = "unhealthy"
    elif degraded_count > 0:
        overall_status = "degraded"

    return HealthResponse(
        status=overall_status,
        timestamp=datetime.now(UTC),
        services=services
    )


@router.get(
    "/status",
    response_model=StatusResponse,
    operation_id="systemStatus",
    summary="System status",
    description="Get detailed system statistics including database info, uptime, and usage metrics",
    responses={
        200: {"description": "System status retrieved successfully"},
        500: {"description": "Internal server error"}
    }
)
async def system_status(
    message_repo: MessageRepositoryDep = None,
    influencer_repo: InfluencerRepositoryDep = None,
):
    """
    System status endpoint
    
    Returns detailed system information and statistics
    """
    db_health = await db.health_check()
    db_stats = DatabaseStats(
        connected=db_health.status == "up",
        pool_size=db_health.pool_size,
        active_connections=db_health.pool_size if db_health.status == "up" else None
    )

    try:
        total_conversations = await db.fetchval("SELECT COUNT(*) FROM conversations")
        total_messages = await message_repo.count_all()
        active_influencers = await influencer_repo.count_all()
    except Exception:
        total_conversations = 0
        total_messages = 0
        active_influencers = 0

    system_stats = SystemStatistics(
        total_conversations=total_conversations,
        total_messages=total_messages,
        active_influencers=active_influencers
    )

    uptime_seconds = int(time.time() - app_start_time)

    return StatusResponse(
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        uptime_seconds=uptime_seconds,
        database=db_stats,
        statistics=system_stats,
        timestamp=datetime.now(UTC)
    )


