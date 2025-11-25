"""
Database connection management using AsyncPG
"""
import asyncpg
from typing import Optional
from loguru import logger
from src.config import settings


class Database:
    """Async PostgreSQL database connection manager"""
    
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
    
    async def connect(self) -> None:
        """Create database connection pool"""
        try:
            self.pool = await asyncpg.create_pool(
                dsn=settings.database_url,
                min_size=settings.db_pool_min_size,
                max_size=settings.db_pool_max_size,
                timeout=settings.db_pool_timeout,
                command_timeout=60
            )
            logger.info(
                f"Database pool created: min={settings.db_pool_min_size}, "
                f"max={settings.db_pool_max_size}"
            )
            
            # Test connection
            async with self.pool.acquire() as conn:
                version = await conn.fetchval("SELECT version()")
                logger.info(f"Connected to database: {version}")
                
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise
    
    async def disconnect(self) -> None:
        """Close database connection pool"""
        if self.pool:
            await self.pool.close()
            logger.info("Database pool closed")
    
    async def execute(self, query: str, *args) -> str:
        """Execute a query without returning results"""
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)
    
    async def fetch(self, query: str, *args) -> list:
        """Fetch multiple rows"""
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)
    
    async def fetchone(self, query: str, *args):
        """Fetch a single row"""
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)
    
    async def fetchval(self, query: str, *args):
        """Fetch a single value"""
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, *args)
    
    async def health_check(self) -> dict:
        """Check database health"""
        try:
            if not self.pool:
                return {"status": "down", "error": "Pool not initialized"}
            
            import time
            start = time.time()
            
            async with self.pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            
            latency_ms = int((time.time() - start) * 1000)
            
            return {
                "status": "up",
                "latency_ms": latency_ms,
                "pool_size": self.pool.get_size(),
                "pool_free": self.pool.get_idle_size()
            }
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return {"status": "down", "error": str(e)}


# Global database instance
db = Database()


