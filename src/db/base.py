"""
Database connection management using SQLAlchemy + asyncpg (PostgreSQL)
Replaces the previous aiosqlite implementation.
"""
import time
import uuid
import re
from loguru import logger
from sqlalchemy.ext.asyncio import create_async_engine, AsyncConnection
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from src.config import settings
from src.models.internal import DatabaseHealth


class Database:
    """Async PostgreSQL database connection manager"""

    def __init__(self):
        self._engine = None

    async def connect(self) -> None:
        """Create database engine"""
        try:
            # Create async engine with pooling
            self._engine = create_async_engine(
                settings.database_url,
                echo=settings.debug,
                pool_size=settings.database_pool_size,
                pool_timeout=settings.database_pool_timeout,
                pool_pre_ping=True,  # Check connection health before checkout
            )

            # Verification
            async with self._engine.connect() as conn:
                result = await conn.execute(text("SELECT version()"))
                version = result.scalar()
                logger.info(f"Connected to PostgreSQL: {version}")

        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    async def disconnect(self) -> None:
        """Close database engine"""
        if self._engine:
            await self._engine.dispose()
            self._engine = None
            logger.info("Database engine disposed")

    def _convert_to_sqlalchemy_params(self, query: str, args: tuple) -> tuple[str, dict]:
        """
        Convert $1 style placeholders to :p_1 style for SQLAlchemy text()
        Returns (new_query, params_dict)
        """
        # Map parameters to a dictionary { "p_1": arg1, "p_2": arg2 }
        params = {f"p_{i+1}": arg for i, arg in enumerate(args)}
        
        # Replace $N with :p_N
        # We look for $ followed by digits
        def replace_match(match):
            idx = match.group(0)[1:] # remove $
            return f":p_{idx}"
            
        new_query = re.sub(r"\$(\d+)", replace_match, query)
        
        # Also fix any SQLite specific date functions if leftovers exist (though _convert_query did the reverse)
        # Postgres uses NOW(), so we should be good if the original query had NOW()
        # Just in case, if there are datetime('now'), revert them? 
        # The previous code changed NOW() to datetime('now').  The repos use NOW().
        # So we just assume Reposaries have valid SQL except for placeholders.
        
        return new_query, params

    async def execute(self, query: str, *args) -> str:
        """Execute a query without returning results"""
        if not self._engine:
            raise RuntimeError("Database engine not initialized")

        sqlalchemy_query, params = self._convert_to_sqlalchemy_params(query, args)
        start_time = time.time()

        try:
            async with self._engine.begin() as conn:
                result = await conn.execute(text(sqlalchemy_query), params)
                duration_ms = int((time.time() - start_time) * 1000)
                if duration_ms > 100:
                    logger.warning(f"Slow query ({duration_ms}ms): {query[:200]}")
                return f"Rows affected: {result.rowcount}"
        except Exception as e:
            logger.error(f"Execute error: {e}, Query: {query[:100]}")
            # SQLAlchemy `begin()` context manager automatically rolls back on exception
            raise

    async def fetch(self, query: str, *args) -> list[dict]:
        """Fetch multiple rows"""
        if not self._engine:
            raise RuntimeError("Database engine not initialized")

        sqlalchemy_query, params = self._convert_to_sqlalchemy_params(query, args)
        start_time = time.time()

        try:
            async with self._engine.connect() as conn:
                # Use stream execution for potentially large results, though fetch implies loading all
                result = await conn.execute(text(sqlalchemy_query), params)
                
                # Convert rows to dicts
                # .mappings() returns MappingResult which yields RowMapping (dict-like)
                rows = result.mappings().all()
                
                duration_ms = int((time.time() - start_time) * 1000)
                # Convert RowMapping to native dict
                row_list = [dict(row) for row in rows]
                
                if duration_ms > 100:
                    logger.warning(f"Slow query ({duration_ms}ms, {len(row_list)} rows): {query[:200]}")
                return row_list
        except Exception as e:
            logger.error(f"Fetch error: {e}, Query: {query[:100]}")
            raise

    async def fetchone(self, query: str, *args) -> dict | None:
        """Fetch a single row"""
        if not self._engine:
            raise RuntimeError("Database engine not initialized")

        sqlalchemy_query, params = self._convert_to_sqlalchemy_params(query, args)
        start_time = time.time()

        try:
            async with self._engine.connect() as conn:
                result = await conn.execute(text(sqlalchemy_query), params)
                row = result.mappings().one_or_none()
                
                duration_ms = int((time.time() - start_time) * 1000)
                if duration_ms > 50:
                    logger.warning(f"Slow query ({duration_ms}ms): {query[:200]}")
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Fetchone error: {e}, Query: {query[:100]}")
            raise

    async def fetchval(self, query: str, *args):
        """Fetch a single value"""
        if not self._engine:
            raise RuntimeError("Database engine not initialized")

        sqlalchemy_query, params = self._convert_to_sqlalchemy_params(query, args)

        try:
            async with self._engine.connect() as conn:
                result = await conn.execute(text(sqlalchemy_query), params)
                return result.scalar()
        except Exception as e:
            logger.error(f"Fetchval error: {e}, Query: {query[:100]}")
            raise

    def generate_uuid(self) -> str:
        """Generate a UUID for use as primary key"""
        return str(uuid.uuid4())

    async def health_check(self) -> DatabaseHealth:
        """Check database health"""
        try:
            if not self._engine:
                return DatabaseHealth(
                    status="down",
                    error="Engine not initialized",
                    latency_ms=None,
                    database="postgres",
                    path=settings.database_url.split("@")[-1], # Mask password
                    size_mb=0.0,
                    pool_size=settings.database_pool_size
                )

            start = time.time()
            async with self._engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            latency_ms = int((time.time() - start) * 1000)
            
            # Estimate DB size (optional, generic query)
            db_size_mb = 0.0 # Requires extensive permissions to query detailed size sometimes

            return DatabaseHealth(
                status="up",
                latency_ms=latency_ms,
                database="postgres",
                path=settings.database_url.split("@")[-1],
                size_mb=db_size_mb,
                pool_size=settings.database_pool_size,
                error=None
            )

        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return DatabaseHealth(
                status="down",
                error=str(e),
                latency_ms=None,
                database="postgres",
                path="unknown",
                size_mb=0.0,
                pool_size=0
            )

db = Database()

async def init_db():
    await db.connect()

async def close_db():
    await db.disconnect()
