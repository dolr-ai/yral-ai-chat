"""
Database connection management - PostgreSQL Only
"""

import abc
import asyncio
import time
import uuid
from typing import Any

import asyncpg
from loguru import logger

from src.config import settings
from src.core.metrics import (
    db_connections_active,
    db_query_duration_seconds,
)
from src.models.internal import DatabaseHealth


# Define custom exceptions for database-agnostic error handling
class DatabaseError(Exception):
    """Base exception for database errors"""


class DatabaseIntegrityError(DatabaseError):
    """Raised when an integrity constraint is violated (e.g. unique constraint)"""


class DatabaseConnectionError(DatabaseError):
    """Raised when connection to database fails"""


class DatabaseConnectionPoolTimeoutError(DatabaseError):
    """Raised when connection pool times out"""


class DatabaseInterface(abc.ABC):
    """Abstract base class for database interfaces"""

    @abc.abstractmethod
    async def connect(self) -> None:
        """Establish connection to the database"""

    @abc.abstractmethod
    async def disconnect(self) -> None:
        """Close connection to the database"""

    @abc.abstractmethod
    async def execute(self, query: str, *args) -> str:
        """Execute a query without returning results"""

    @abc.abstractmethod
    async def fetch(self, query: str, *args) -> list[dict[str, Any]]:
        """Fetch multiple rows"""

    @abc.abstractmethod
    async def fetchone(self, query: str, *args) -> dict[str, Any] | None:
        """Fetch a single row"""

    @abc.abstractmethod
    async def fetchval(self, query: str, *args) -> Any:
        """Fetch a single value"""

    @abc.abstractmethod
    async def health_check(self) -> DatabaseHealth:
        """Check database health"""

    def generate_uuid(self) -> str:
        """Generate a UUID for use as primary key"""
        return str(uuid.uuid4())


class PostgresDatabase(DatabaseInterface):
    """Async PostgreSQL database implementation using asyncpg"""

    def __init__(self):
        self._pool: asyncpg.Pool | None = None
        
    async def connect(self) -> None:
        retries = 5
        retry_delay = 1.0
        
        for attempt in range(retries):
            try:
                self._pool = await asyncpg.create_pool(
                    user=settings.postgres_user,
                    password=settings.postgres_password,
                    host=settings.postgres_host,
                    port=settings.postgres_port,
                    database=settings.postgres_database,
                    min_size=settings.postgres_pool_min_size,
                    max_size=settings.postgres_pool_max_size,
                    command_timeout=settings.database_pool_timeout,  # Prevent hanging queries
                    max_inactive_connection_lifetime=300.0,          # Recycle stale connections
                    server_settings={
                        "application_name": settings.app_name,
                        "timezone": "UTC",
                    }
                )
                logger.info(
                    f"Connected to PostgreSQL database at {settings.postgres_host}:{settings.postgres_port}/{settings.postgres_database}"
                )
                
                # Test the connection immediately
                async with self._pool.acquire() as conn:
                    await conn.fetchval("SELECT 1")
                
                db_connections_active.set(settings.postgres_pool_min_size)
                return

            except (OSError, asyncpg.PostgresError) as e:
                # If it's the last attempt, log critical error and raise
                if attempt == retries - 1:
                    logger.critical(f"Failed to connect to PostgreSQL after {retries} attempts: {e}")
                    raise DatabaseConnectionError(f"Connection failed: {e}") from e
                
                # Exponential backoff
                wait_time = retry_delay * (2 ** attempt)
                logger.warning(f"Failed to connect to PostgreSQL (attempt {attempt + 1}/{retries}): {e}. Retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
            except Exception as e:
                logger.error(f"Unexpected error connecting to PostgreSQL: {e}")
                raise DatabaseConnectionError(str(e)) from e

    async def disconnect(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("PostgreSQL connection pool closed")

    async def execute(self, query: str, *args) -> str:
        if not self._pool:
            raise RuntimeError("Database connection pool not initialized")
        
        start_exec = time.time()
        try:
            result = await self._pool.execute(query, *args)
            exec_duration_ms = int((time.time() - start_exec) * 1000)
            db_query_duration_seconds.labels(operation="execute").observe(exec_duration_ms / 1000.0)
            return result
        except asyncpg.UniqueViolationError as e:
            raise DatabaseIntegrityError(str(e)) from e
        except Exception as e:
            logger.error(f"Execute error: {e}, Query: {query[:100]}")
            raise DatabaseError(str(e)) from e

    async def fetch(self, query: str, *args) -> list[dict[str, Any]]:
        if not self._pool:
            raise RuntimeError("Database connection pool not initialized")
        
        start_time = time.time()
        try:
            rows = await self._pool.fetch(query, *args)
            duration_ms = int((time.time() - start_time) * 1000)
            db_query_duration_seconds.labels(operation="fetch").observe(duration_ms / 1000.0)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Fetch error: {e}, Query: {query[:100]}")
            raise DatabaseError(str(e)) from e

    async def fetchone(self, query: str, *args) -> dict[str, Any] | None:
        if not self._pool:
            raise RuntimeError("Database connection pool not initialized")
        
        start_time = time.time()
        try:
            row = await self._pool.fetchrow(query, *args)
            duration_ms = int((time.time() - start_time) * 1000)
            db_query_duration_seconds.labels(operation="fetchone").observe(duration_ms / 1000.0)
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Fetchone error: {e}, Query: {query[:100]}")
            raise DatabaseError(str(e)) from e

    async def fetchval(self, query: str, *args) -> Any:
        if not self._pool:
            raise RuntimeError("Database connection pool not initialized")
        
        try:
            return await self._pool.fetchval(query, *args)
        except Exception as e:
            logger.error(f"Fetchval error: {e}, Query: {query[:100]}")
            raise DatabaseError(str(e)) from e

    async def health_check(self) -> DatabaseHealth:
        if not self._pool:
            return DatabaseHealth(
                status="down",
                error="Connection pool not initialized",
                latency_ms=None,
                database="postgresql",
                path=f"{settings.postgres_host}/{settings.postgres_database}",
                size_mb=0.0,
                pool_size=0,
            )
        try:
            start = time.time()
            await self._pool.fetchval("SELECT 1")
            latency_ms = int((time.time() - start) * 1000)
            
            # Ensure pool stats are available or catch attribute error if older asyncpg
            pool_size = self._pool.get_size() if hasattr(self._pool, "get_size") else 0
            
            return DatabaseHealth(
                status="up",
                latency_ms=latency_ms,
                database="postgresql",
                path=f"{settings.postgres_host}/{settings.postgres_database}",
                size_mb=0.0, # Not easily available for remote PG without extra queries
                pool_size=pool_size,
                error=None,
            )
        except Exception as e:
            return DatabaseHealth(
                status="down",
                error=str(e),
                latency_ms=None,
                database="postgresql",
                path=f"{settings.postgres_host}/{settings.postgres_database}",
                size_mb=0.0,
                pool_size=0,
            )


# Global database instance - Always PostgreSQL now
db = PostgresDatabase()


async def init_db():
    """Initialize database connection (called on startup)"""
    await db.connect()


async def close_db():
    """Close database connection (called on shutdown)"""
    await db.disconnect()
