"""
Health check and status endpoints
"""
import os
import subprocess
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


def check_litestream_process() -> ServiceHealth:  # noqa: PLR0911
    """
    Check if Litestream replication process is running
    Returns ServiceHealth with status and optional error message
    """
    # Check if Litestream is enabled
    enable_litestream = os.getenv("ENABLE_LITESTREAM", "true").lower() == "true"
    has_credentials = all([
        os.getenv("LITESTREAM_BUCKET"),
        os.getenv("LITESTREAM_ACCESS_KEY_ID"),
        os.getenv("LITESTREAM_SECRET_ACCESS_KEY")
    ])
    
    # If Litestream is disabled or not configured, return as not applicable
    if not enable_litestream or not has_credentials:
        return ServiceHealth(
            status="up",  # Not a problem if disabled
            error=None
        )
    
    # Check if litestream process is running
    try:
        # Use ps to check for litestream replicate process
        result = subprocess.run(
            ["ps", "aux"],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=2,
            check=False
        )
        
        if result.returncode == 0:
            # Look for litestream replicate process
            if "litestream replicate" in result.stdout:
                return ServiceHealth(
                    status="up",
                    error=None
                )
            return ServiceHealth(
                status="degraded",
                error="Litestream process not found (replication may not be running)"
            )
        # If ps command fails, try alternative method
        # Check if litestream binary exists and is accessible
        try:
            subprocess.run(
                ["litestream", "version"],  # noqa: S607
                capture_output=True,
                timeout=2,
                check=False
            )
            return ServiceHealth(
                status="degraded",
                error="Cannot verify Litestream process status"
            )
        except FileNotFoundError:
            return ServiceHealth(
                status="degraded",
                error="Litestream binary not found"
            )
    except subprocess.TimeoutExpired:
        return ServiceHealth(
            status="degraded",
            error="Litestream process check timed out"
        )
    except Exception as e:
        logger.warning(f"Error checking Litestream process: {e}")
        return ServiceHealth(
            status="degraded",
            error=f"Error checking Litestream: {e!s}"
        )


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
    Health check endpoint.
    Checks database connectivity and circuit breaker states (no external API calls).
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

    # Check Litestream replication process
    litestream_health = check_litestream_process()
    services["litestream"] = litestream_health

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
    """Get detailed system statistics including database info, uptime, and usage metrics"""
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


