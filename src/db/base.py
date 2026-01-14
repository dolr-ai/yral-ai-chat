"""
Database connection management using aiosqlite (SQLite)
Configured for use with Litestream for real-time S3 backups
"""
import asyncio
import os
import re
import secrets
import time
import uuid
from pathlib import Path

import aiosqlite
from loguru import logger

from src.config import settings
from src.models.internal import DatabaseHealth


class DatabaseConnectionPoolTimeoutError(Exception):
    """Raised when database connection pool times out"""


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
        busy_timeout_ms = int(self.timeout * 1000)
        conn = await aiosqlite.connect(
            self.db_path,
            timeout=busy_timeout_ms / 1000.0
        )

        await conn.execute("PRAGMA foreign_keys = ON")
        await conn.execute("PRAGMA journal_mode = WAL")
        
        # Litestream optimization: Prevent WAL from growing too large
        await conn.execute("PRAGMA wal_autocheckpoint = 4000")
        await conn.execute("PRAGMA journal_size_limit = 16777216") # 16MB
        
        # Timeout handling
        # We set a high busy_timeout to allow queuing during checkpoints
        actual_timeout = max(busy_timeout_ms, 60000)
        await conn.execute(f"PRAGMA busy_timeout = {actual_timeout}")
        
        await conn.execute("PRAGMA synchronous = NORMAL")
        
        # Verify timeout setting
        async with conn.execute("PRAGMA busy_timeout") as cursor:
            row = await cursor.fetchone()
            timeout_setting = row[0] if row else "unknown"
            if self._created_connections == 0: # Only log for the first connection to reduce noise
                logger.info(f"Database initialized with busy_timeout={timeout_setting}ms (requested={actual_timeout}ms)")

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
            raise DatabaseConnectionPoolTimeoutError("Database connection pool timeout") from e

    async def release(self, conn: aiosqlite.Connection):
        """Release a connection back to the pool"""
        try:
            await self._pool.put(conn)
        except asyncio.QueueFull:
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
        raw_db_path = os.getenv("TEST_DATABASE_PATH", settings.database_path)
        self.db_path: str = self._resolve_db_path(raw_db_path)
        self._pool: ConnectionPool | None = None

    @staticmethod
    def _resolve_db_path(db_path: str) -> str:
        """Resolve relative database path to absolute path based on project root"""
        if Path(db_path).is_absolute():
            return db_path
        
        # Use /app in Docker, otherwise resolve relative to project root
        if Path("/app").exists() and Path("/app/migrations").exists():
            project_root = Path("/app")
        else:
            project_root = Path(__file__).parent.parent.parent
        
        resolved_path = (project_root / db_path).resolve()
        return str(resolved_path)

    async def connect(self) -> None:
        """Create database connection pool"""
        try:
            raw_db_path = os.getenv("TEST_DATABASE_PATH", settings.database_path)
            self.db_path = self._resolve_db_path(raw_db_path)
            
            if self.db_path != ":memory:":
                Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

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

            conn = await self._pool.acquire()
            try:
                async with conn.execute("SELECT sqlite_version()") as cursor:
                    row = await cursor.fetchone()
                    if row:
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
        if not self._pool:
            raise RuntimeError("Database connection pool not initialized")
        query = self._convert_query(query)
        conn = await self._pool.acquire()
        start_time = time.time()
        max_retries = 10
        retry_delay = 0.2
        last_error: Exception | None = None
        
        try:
            for attempt in range(max_retries):
                try:
                    async with conn.execute(query, args) as cursor:
                        await conn.commit()
                        duration_ms = int((time.time() - start_time) * 1000)
                        if duration_ms > 100:
                            logger.warning(f"Slow query ({duration_ms}ms): {query[:200]}")
                        return f"Rows affected: {cursor.rowcount}"
                except Exception as e:
                    last_error = e
                    error_str = str(e).lower()
                    
                    # Always rollback on any execution error to prevent transaction leaks
                    try:
                        await conn.rollback()
                    except Exception as rollback_err:
                        logger.error(f"Failed to rollback after execution error: {rollback_err}")

                    if ("database is locked" in error_str or "locked" in error_str) and attempt < max_retries - 1:
                        # Random jitter to prevent thundering herd
                        # Increased backoff: 0.2, 0.4, 0.8, 1.6, 3.2, 6.4, 12.8...
                        actual_delay = retry_delay * (2 ** attempt) + (secrets.SystemRandom().random() * 0.5)
                        logger.warning(f"Database locked, retrying in {actual_delay:.2f}s (attempt {attempt + 1}/{max_retries})")
                        await asyncio.sleep(actual_delay)
                        continue
                    
                    # Enhanced logging for FK constraint failures
                    if "foreign key" in error_str:
                        logger.error(
                            f"FOREIGN KEY constraint failed. Query: {query[:200]}, "
                            f"Args count: {len(args)}, Error: {e}"
                        )
                    else:
                        logger.error(f"Execute error: {e}, Query: {query[:100]}")
                    raise
            if last_error:
                raise last_error
            raise RuntimeError("Failed to execute query after retries")
        finally:
            await self._pool.release(conn)

    async def fetch(self, query: str, *args) -> list[dict[str, str | int | float | bool | None]]:
        """Fetch multiple rows"""
        if not self._pool:
            raise RuntimeError("Database connection pool not initialized")
        query = self._convert_query(query)
        conn = await self._pool.acquire()
        start_time = time.time()
        try:
            async with conn.execute(query, args) as cursor:
                rows = await cursor.fetchall()
                duration_ms = int((time.time() - start_time) * 1000)
                row_list = [dict(row) for row in rows]
                if duration_ms > 100:
                    logger.warning(f"Slow query ({duration_ms}ms, {len(row_list)} rows): {query[:200]}")
                return row_list
        except Exception as e:
            logger.error(f"Fetch error: {e}, Query: {query[:100]}")
            raise
        finally:
            await self._pool.release(conn)

    async def fetchone(self, query: str, *args) -> dict[str, str | int | float | bool | None] | None:
        """Fetch a single row"""
        if not self._pool:
            raise RuntimeError("Database connection pool not initialized")
        query = self._convert_query(query)
        conn = await self._pool.acquire()
        start_time = time.time()
        try:
            async with conn.execute(query, args) as cursor:
                row = await cursor.fetchone()
                duration_ms = int((time.time() - start_time) * 1000)
                if duration_ms > 50:
                    logger.warning(f"Slow query ({duration_ms}ms): {query[:200]}")
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Fetchone error: {e}, Query: {query[:100]}")
            raise
        finally:
            await self._pool.release(conn)

    async def fetchval(self, query: str, *args) -> str | int | float | bool | None:
        """Fetch a single value"""
        if not self._pool:
            raise RuntimeError("Database connection pool not initialized")
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
        query = re.sub(r"\$\d+", "?", query)
        query = re.sub(r"\bNOW\(\)", "datetime('now')", query, flags=re.IGNORECASE)
        query = re.sub(r"\s+=\s+true\b", " = 1", query, flags=re.IGNORECASE)
        return re.sub(r"\s+=\s+false\b", " = 0", query, flags=re.IGNORECASE)


    def generate_uuid(self) -> str:
        """Generate a UUID for use as primary key"""
        return str(uuid.uuid4())

    async def health_check(self) -> DatabaseHealth:
        """Check database health"""
        try:
            if not self._pool:
                return DatabaseHealth(
                    status="down",
                    error="Connection pool not initialized",
                    latency_ms=None,
                    database="sqlite",
                    path=self.db_path,
                    size_mb=0.0,
                    pool_size=settings.database_pool_size
                )

            start = time.time()

            await self.fetchval("SELECT 1")

            latency_ms = int((time.time() - start) * 1000)

            db_size_mb = 0.0
            if Path(self.db_path).exists():
                db_size_mb = round(Path(self.db_path).stat().st_size / (1024 * 1024), 2)
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return DatabaseHealth(
                status="down",
                error=str(e),
                latency_ms=None,
                database="sqlite",
                path=self.db_path,
                size_mb=0.0,
                pool_size=settings.database_pool_size
            )
        else:
            return DatabaseHealth(
                status="up",
                latency_ms=latency_ms,
                database="sqlite",
                path=self.db_path,
                size_mb=db_size_mb,
                pool_size=settings.database_pool_size,
                error=None
            )

db = Database()


async def init_db():
    """Initialize database connection (called on startup)"""
    await db.connect()


async def close_db():
    """Close database connection (called on shutdown)"""
    await db.disconnect()
