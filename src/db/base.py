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
from src.core.metrics import (
    db_connections_active,
    db_query_duration_seconds,
)
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
        # Create first connection sequentially to ensure DB is in WAL mode and safe
        # This prevents race conditions when multiple connections try to set journal_mode=WAL
        if self.pool_size > 0:
            first_conn = await self._create_connection()
            await self._pool.put(first_conn)

        # Create remaining connections in parallel
        if self.pool_size > 1:
            tasks = [self._create_connection() for _ in range(self.pool_size - 1)]
            connections = await asyncio.gather(*tasks)
            
            for conn in connections:
                await self._pool.put(conn)

    async def _create_connection(self) -> aiosqlite.Connection:
        """Create a new database connection"""
        busy_timeout_ms = int(self.timeout * 1000)
        conn = await aiosqlite.connect(
            self.db_path,
            timeout=busy_timeout_ms / 1000.0,
            isolation_level=None
        )

        await conn.execute("PRAGMA foreign_keys = ON")
        
        actual_timeout = max(busy_timeout_ms, 60000)
        
        if self.db_path != ":memory:":
            try:
                await conn.execute("PRAGMA journal_mode = WAL")
            except Exception as e:
                logger.warning(f"Failed to set WAL mode: {e}")

            # CRITICAL: Disable SQLite's built-in WAL autocheckpoint.
            # Litestream holds continuous read locks on the WAL during replication.
            # SQLite's TRUNCATE checkpoint requires ZERO active readers to succeed.
            # With pool connections + Litestream all holding read locks, autocheckpoint
            # was silently failing every time, causing the WAL to grow unbounded (600MB+).
            # Setting to 0 gives Litestream exclusive ownership of checkpointing —
            # its own forced-truncate mechanism coordinates safely with its own locks.
            await conn.execute("PRAGMA wal_autocheckpoint = 0")
            
            # Keep journal size limit reasonable (64MB)
            await conn.execute("PRAGMA journal_size_limit = 67108864")
            
            # Timeout handling
            # We set a high busy_timeout to allow queuing during checkpoints
            actual_timeout = max(busy_timeout_ms, 60000)
            await conn.execute(f"PRAGMA busy_timeout = {actual_timeout}")
            # Performance tuning
            await conn.execute("PRAGMA synchronous = NORMAL")
            # Reduced from 256MB to 32MB: the 256MB mmap per connection multiplied
            # across 10 pool connections was a major OOM contributor.
            await conn.execute("PRAGMA mmap_size = 33554432")  # 32MB
        # Reduced from 64MB to 16MB to lower per-connection memory footprint.
        await conn.execute("PRAGMA cache_size = -16000")    # 16MB (negative value = kb)
        await conn.execute("PRAGMA temp_store = MEMORY")
        
        # Verify timeout setting
        async with conn.execute("PRAGMA busy_timeout") as cursor:
            row = await cursor.fetchone()
            timeout_setting = row[0] if row else "unknown"
            if self._created_connections == 0:  # Only log for the first connection to reduce noise
                logger.info(
                    f"Database initialized with busy_timeout={timeout_setting}ms (requested={actual_timeout}ms)"
                )

        conn.row_factory = aiosqlite.Row

        self._created_connections += 1
        return conn

    async def acquire(self) -> aiosqlite.Connection:
        """Acquire a connection from the pool"""
        try:
            return await asyncio.wait_for(self._pool.get(), timeout=self.timeout)
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
            try:
                # Safe optimization: HELP SQLite query planner by analyzing data before close
                await conn.execute("PRAGMA optimize")
            except Exception as e:
                logger.debug(f"PRAGMA optimize failed during shutdown: {e}")
            await conn.close()
            db_connections_active.dec()
        logger.info(f"Closed all {self._created_connections} database connections")


class Database:
    """Async SQLite database connection manager with pooling"""

    def __init__(self):
        raw_db_path = os.getenv("TEST_DATABASE_PATH", settings.database_path)
        self.db_path: str = self._resolve_db_path(raw_db_path)
        self._pool: ConnectionPool | None = None

    async def _apply_migrations(self, conn: aiosqlite.Connection):
        """Apply all migrations to the database (used for proper :memory: initialization)"""
        logger.info("Applying migrations to in-memory database...")
        project_root = Path(__file__).parent.parent.parent
        migrations_dir = project_root / "migrations" / "sqlite"
        
        await conn.execute("CREATE TABLE IF NOT EXISTS _migrations (filename TEXT PRIMARY KEY, applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        
        applied_rows = await conn.execute_fetchall("SELECT filename FROM _migrations")
        applied = {row[0] for row in applied_rows}
        
        # Sort files to ensure order
        if not migrations_dir.exists():
             logger.warning(f"Migrations directory not found: {migrations_dir}")
             return

        migration_files = sorted([f.name for f in migrations_dir.iterdir() if f.name.endswith(".sql")])
        
        for filename in migration_files:
            if filename in applied:
                continue
                
            logger.info(f"Applying migration: {filename}")
            file_path = migrations_dir / filename
            with file_path.open() as f:
                sql_script = f.read()
                
            try:
                await conn.executescript(sql_script)
                await conn.execute("INSERT INTO _migrations (filename) VALUES (?)", (filename,))
                await conn.commit()
            except Exception as e:
                logger.error(f"Migration failed for {filename}: {e}")
                raise

    @staticmethod
    def _resolve_db_path(db_path: str) -> str:
        """Resolve relative database path to absolute path based on project root"""
        if db_path == ":memory:":
            return db_path
            
        if Path(db_path).is_absolute():
            return db_path

        # Use /app in Docker, otherwise resolve relative to project root
        project_root = Path("/app") if Path("/app/migrations").exists() else Path(__file__).parent.parent.parent
        return str((project_root / db_path).resolve())

    async def connect(self) -> None:
        """Create database connection pool"""
        try:
            raw_db_path = os.getenv("TEST_DATABASE_PATH", settings.database_path)
            self.db_path = self._resolve_db_path(raw_db_path)
            
            # Ensure the database directory exists (skip for in-memory)
            if self.db_path != ":memory:":
                Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

            self._pool = ConnectionPool(
                db_path=self.db_path, pool_size=settings.database_pool_size, timeout=settings.database_pool_timeout
            )
            await self._pool.initialize()

            logger.info(
                f"Connected to SQLite database: {self.db_path} "
                f"(pool size: {settings.database_pool_size})"
            )
            db_connections_active.set(settings.database_pool_size)


            conn = await self._pool.acquire()
            try:
                # If using in-memory DB, apply migrations on the first connection
                if self.db_path == ":memory:":
                    await self._apply_migrations(conn)

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

    async def periodic_wal_checkpoint(self, interval_seconds: int = 300) -> None:
        """
        Background task to periodically run PRAGMA wal_checkpoint(PASSIVE).
        This is a safety net for when wal_autocheckpoint=0 is set (to allow Litestream
        to manage checkpointing). It ensures the WAL doesn't grow unbounded if
        Litestream replication is delayed or fails to checkpoint.
        """
        if self.db_path == ":memory:":
            return

        while True:
            await asyncio.sleep(interval_seconds)
            if not self._pool:
                continue

            try:
                conn = await self._pool.acquire()
                try:
                    # PASSIVE checkpoint: flushes as many frames as possible
                    # without blocking other readers/writers.
                    async with conn.execute("PRAGMA wal_checkpoint(PASSIVE)") as cursor:
                        row = await cursor.fetchone()
                        if row:
                            logger.info(
                                f"Periodic WAL checkpoint: log={row[1]} pages, "
                                f"checkpointed={row[2]}, busy={row[0]}"
                            )
                finally:
                    await self._pool.release(conn)
            except Exception as e:
                logger.warning(f"Periodic WAL checkpoint failed (non-fatal): {e}")

    async def eager_checkpoint(self) -> None:
        """Run an immediate PASSIVE checkpoint (e.g., on startup)."""
        if not self._pool or self.db_path == ":memory:":
            return

        try:
            conn = await self._pool.acquire()
            try:
                async with conn.execute("PRAGMA wal_checkpoint(PASSIVE)") as cursor:
                    row = await cursor.fetchone()
                    if row:
                        logger.info(
                            f"Eager WAL checkpoint: log={row[1]} pages, "
                            f"checkpointed={row[2]}, busy={row[0]}"
                        )
            finally:
                await self._pool.release(conn)
        except Exception as e:
            logger.warning(f"Eager WAL checkpoint failed (non-fatal): {e}")

    async def execute(self, query: str, *args) -> str:
        """Execute a query without returning results"""
        if not self._pool:
            raise RuntimeError("Database connection pool not initialized")
        query = self._convert_query(query)
        
        start_wait = time.time()
        conn = await self._pool.acquire()
        wait_duration_ms = int((time.time() - start_wait) * 1000)
        
        max_retries = 10
        retry_delay = 0.2
        last_error: Exception | None = None

        try:
            for attempt in range(max_retries):
                start_exec = time.time()
                try:
                    # BEGIN IMMEDIATE to acquire write lock early and prevent deadlock
                    await conn.execute("BEGIN IMMEDIATE")
                    async with conn.execute(query, args) as cursor:
                        await conn.commit()
                        
                        exec_duration_ms = int((time.time() - start_exec) * 1000)
                        total_duration_ms = wait_duration_ms + exec_duration_ms
                        
                        db_query_duration_seconds.labels(operation="execute").observe(exec_duration_ms / 1000.0)

                        if total_duration_ms > 100:
                            logger.warning(
                                f"Slow execute ({total_duration_ms}ms total): "
                                f"wait_conn={wait_duration_ms}ms, "
                                f"exec_query={exec_duration_ms}ms, "
                                f"attempt={attempt + 1}. Query: {query[:200]}"
                            )
                        
                        db_query_duration_seconds.labels(operation="execute").observe(exec_duration_ms / 1000.0)
                        return f"Rows affected: {cursor.rowcount}"

                except Exception as e:
                    last_error = e
                    # Rollback on error
                    try:
                        await conn.rollback()
                    except Exception as rollback_err:
                        logger.error(f"Failed to rollback after execution error: {rollback_err}")
                        
                    error_str = str(e).lower()
                    if ("database is locked" in error_str or "locked" in error_str) and attempt < max_retries - 1:
                        actual_delay = retry_delay * (2 ** attempt) + (secrets.SystemRandom().random() * 0.5)
                        logger.warning(f"Database locked, retrying in {actual_delay:.2f}s (attempt {attempt + 1}/{max_retries})")
                        await asyncio.sleep(actual_delay)
                        continue
                    
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
                db_query_duration_seconds.labels(operation="fetch").observe(duration_ms / 1000.0)
                row_list = [dict(row) for row in rows]

                # Commit if it's a mutation (e.g. INSERT ... RETURNING)
                if query.strip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
                    await conn.commit()

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

                # Commit if it's a mutation (e.g. INSERT ... RETURNING)
                if query.strip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
                    await conn.commit()

                duration_ms = int((time.time() - start_time) * 1000)
                db_query_duration_seconds.labels(operation="fetchone").observe(duration_ms / 1000.0)
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
        start_time = time.time()
        try:
            async with conn.execute(query, args) as cursor:
                start_time = time.time()
                row = await cursor.fetchone()
                duration_ms = int((time.time() - start_time) * 1000)
                db_query_duration_seconds.labels(operation="fetchval").observe(duration_ms / 1000.0)
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
                    pool_size=settings.database_pool_size,
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
                pool_size=settings.database_pool_size,
            )
        else:
            return DatabaseHealth(
                status="up",
                latency_ms=latency_ms,
                database="sqlite",
                path=self.db_path,
                size_mb=db_size_mb,
                pool_size=settings.database_pool_size,
                error=None,
            )


db = Database()


async def init_db():
    """Initialize database connection (called on startup)"""
    await db.connect()


async def close_db():
    """Close database connection (called on shutdown)"""
    await db.disconnect()
