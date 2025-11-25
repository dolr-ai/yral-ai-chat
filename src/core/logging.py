"""
Logging configuration
"""
import sys
from loguru import logger
from src.config import settings


def setup_logging():
    """Configure loguru logging"""
    
    # Remove default logger
    logger.remove()
    
    # Add console logger
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )
    
    logger.add(
        sys.stdout,
        format=log_format,
        level=settings.log_level,
        colorize=True
    )
    
    # Add file logger
    logger.add(
        "logs/yral_ai_chat.log",
        rotation="100 MB",
        retention="10 days",
        level=settings.log_level,
        format=log_format
    )
    
    logger.info(f"Logging configured: level={settings.log_level}")


# Initialize logging
setup_logging()


