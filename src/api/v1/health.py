"""
Health check and status endpoints
"""
from fastapi import APIRouter
from datetime import datetime
import time
from src.models.responses import HealthResponse, StatusResponse, ServiceHealth, DatabaseStats, SystemStatistics
from src.db.base import db
from src.services.gemini_client import gemini_client
from src.db.repositories import MessageRepository, InfluencerRepository
from src.config import settings

router = APIRouter(tags=["Health"])

# Track app start time
app_start_time = time.time()


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint
    
    Returns status of database and AI services
    """
    # Check database
    db_health = await db.health_check()
    
    # Check Gemini API
    gemini_health = await gemini_client.health_check()
    
    # Overall status
    overall_status = "healthy"
    if db_health["status"] != "up" or gemini_health["status"] != "up":
        overall_status = "unhealthy"
    
    return HealthResponse(
        status=overall_status,
        timestamp=datetime.utcnow(),
        services={
            "database": ServiceHealth(**db_health),
            "gemini_api": ServiceHealth(**gemini_health)
        }
    )


@router.get("/status", response_model=StatusResponse)
async def system_status():
    """
    System status endpoint
    
    Returns detailed system information and statistics
    """
    # Get database stats
    db_health = await db.health_check()
    db_stats = DatabaseStats(
        connected=db_health["status"] == "up",
        pool_size=db_health.get("pool_size"),
        active_connections=db_health.get("pool_size", 0) - db_health.get("pool_free", 0) if db_health["status"] == "up" else None
    )
    
    # Get system statistics
    message_repo = MessageRepository()
    influencer_repo = InfluencerRepository()
    
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
    
    # Calculate uptime
    uptime_seconds = int(time.time() - app_start_time)
    
    return StatusResponse(
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        uptime_seconds=uptime_seconds,
        database=db_stats,
        statistics=system_stats,
        timestamp=datetime.utcnow()
    )


