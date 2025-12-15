"""
Database connection management using aiosqlite (SQLite)
Configured for use with Litestream for real-time S3 backups
"""
import asyncio
import re
import time
import uuid
from pathlib import Path
from typing import Any

import aiosqlite
from loguru import logger

from src.config import settings


class ConnectionPool:
    """Simple connection pool for SQLite"""

    def __init__(self, db_path: str, pool_size: int, timeout: float):
        self.db_path = db_path
        self.pool_size = pool_size
        self.timeout = timeout
        self._pool: asyncio.Queue[aiosqlite.Connection] = asyncio.Queue(maxsize=pool_size)
        self._created_connections = 0

    async def initialize(self):
        """Initialize the connection pool"""
        for _ in range(self.pool_size):
            conn = await self._create_connection()
            await self._pool.put(conn)

    async def _create_connection(self) -> aiosqlite.Connection:
        """Create a new database connection"""
        conn = await aiosqlite.connect(
            self.db_path,
            timeout=self.timeout
        )

        # Enable foreign keys
        await conn.execute("PRAGMA foreign_keys = ON")
        # Enable WAL mode for better concurrency (required for Litestream)
        await conn.execute("PRAGMA journal_mode = WAL")
        # Sync mode for durability with good performance
        await conn.execute("PRAGMA synchronous = NORMAL")
        # Increase cache size for better performance
        await conn.execute("PRAGMA cache_size = -64000")  # 64MB

        # Use Row factory for dict-like access
        conn.row_factory = aiosqlite.Row

        self._created_connections += 1
        return conn

    async def acquire(self) -> aiosqlite.Connection:
        """Acquire a connection from the pool"""
        try:
            return await asyncio.wait_for(
                self._pool.get(),
                timeout=self.timeout
            )
        except TimeoutError as e:
            logger.error("Timeout waiting for database connection from pool")
            raise Exception("Database connection pool timeout") from e

    async def release(self, conn: aiosqlite.Connection):
        """Release a connection back to the pool"""
        try:
            await self._pool.put(conn)
        except asyncio.QueueFull:
            # This shouldn't happen, but close the connection if it does
            await conn.close()
            logger.warning("Connection pool full, closing connection")

    async def close_all(self):
        """Close all connections in the pool"""
        while not self._pool.empty():
            conn = await self._pool.get()
            await conn.close()
        logger.info(f"Closed all {self._created_connections} database connections")


class Database:
    """Async SQLite database connection manager with pooling"""

    def __init__(self):
        self.db_path: str = settings.database_path
        self._pool: ConnectionPool | None = None

    async def connect(self) -> None:
        """Create database connection pool"""
        try:
            # Ensure directory exists
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

            # Initialize connection pool
            self._pool = ConnectionPool(
                db_path=self.db_path,
                pool_size=settings.database_pool_size,
                timeout=settings.database_pool_timeout
            )
            await self._pool.initialize()

            logger.info(
                f"Connected to SQLite database: {self.db_path} "
                f"(pool size: {settings.database_pool_size})"
            )

            # Log SQLite version using a connection from pool
            conn = await self._pool.acquire()
            try:
                async with conn.execute("SELECT sqlite_version()") as cursor:
                    row = await cursor.fetchone()
                    logger.info(f"SQLite version: {row[0]}")
            finally:
                await self._pool.release(conn)

        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    async def disconnect(self) -> None:
        """Close all database connections"""
        if self._pool:
            await self._pool.close_all()
            self._pool = None
            logger.info("Database connection pool closed")

    async def execute(self, query: str, *args) -> str:
        """Execute a query without returning results"""
        query = self._convert_query(query)
        conn = await self._pool.acquire()
        start_time = time.time()
        try:
            async with conn.execute(query, args) as cursor:
                await conn.commit()
                duration_ms = int((time.time() - start_time) * 1000)
                if duration_ms > 100:  # Log slow queries
                    logger.warning(f"Slow query ({duration_ms}ms): {query[:200]}")
                return f"Rows affected: {cursor.rowcount}"
        except Exception as e:
            logger.error(f"Execute error: {e}, Query: {query[:100]}")
            raise
        finally:
            await self._pool.release(conn)

    async def fetch(self, query: str, *args) -> list[dict[str, Any]]:
        """Fetch multiple rows"""
        query = self._convert_query(query)
        conn = await self._pool.acquire()
        start_time = time.time()
        try:
            async with conn.execute(query, args) as cursor:
                rows = await cursor.fetchall()
                duration_ms = int((time.time() - start_time) * 1000)
                if duration_ms > 100:  # Log slow queries
                    logger.warning(f"Slow query ({duration_ms}ms, {len(rows)} rows): {query[:200]}")
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Fetch error: {e}, Query: {query[:100]}")
            raise
        finally:
            await self._pool.release(conn)

    async def fetchone(self, query: str, *args) -> dict[str, Any] | None:
        """Fetch a single row"""
        query = self._convert_query(query)
        conn = await self._pool.acquire()
        start_time = time.time()
        try:
            async with conn.execute(query, args) as cursor:
                row = await cursor.fetchone()
                duration_ms = int((time.time() - start_time) * 1000)
                if duration_ms > 50:  # Log slow single-row queries
                    logger.warning(f"Slow query ({duration_ms}ms): {query[:200]}")
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Fetchone error: {e}, Query: {query[:100]}")
            raise
        finally:
            await self._pool.release(conn)

    async def fetchval(self, query: str, *args) -> Any:
        """Fetch a single value"""
        query = self._convert_query(query)
        conn = await self._pool.acquire()
        try:
            async with conn.execute(query, args) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None
        except Exception as e:
            logger.error(f"Fetchval error: {e}, Query: {query[:100]}")
            raise
        finally:
            await self._pool.release(conn)

    def _convert_query(self, query: str) -> str:
        """Convert PostgreSQL query syntax to SQLite"""
        # Convert $1, $2, etc. to ?
        query = re.sub(r"\$\d+", "?", query)

        # Convert PostgreSQL NOW() to SQLite datetime('now')
        query = re.sub(r"\bNOW\(\)", "datetime('now')", query, flags=re.IGNORECASE)

        # Convert PostgreSQL true/false to SQLite 1/0 in comparisons
        # But be careful not to replace inside strings
        query = re.sub(r"\s+=\s+true\b", " = 1", query, flags=re.IGNORECASE)
        query = re.sub(r"\s+=\s+false\b", " = 0", query, flags=re.IGNORECASE)

        return query

    def generate_uuid(self) -> str:
        """Generate a UUID for use as primary key"""
        return str(uuid.uuid4())

    async def health_check(self) -> dict:
        """Check database health"""
        try:
            if not self._pool:
                return {"status": "down", "error": "Connection pool not initialized"}

            start = time.time()

            await self.fetchval("SELECT 1")

            latency_ms = int((time.time() - start) * 1000)

            # Get database file size
            db_size_mb = 0
            if Path(self.db_path).exists():
                db_size_mb = round(Path(self.db_path).stat().st_size / (1024 * 1024), 2)
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return {"status": "down", "error": str(e)}
        else:
            return {
                "status": "up",
                "latency_ms": latency_ms,
                "database": "sqlite",
                "path": self.db_path,
                "size_mb": db_size_mb,
                "pool_size": settings.database_pool_size
            }


# Global database instance
db = Database()


async def init_db():
    """Initialize database connection (called on startup)"""
    await db.connect()


async def close_db():
    """Close database connection (called on shutdown)"""
    await db.disconnect()
