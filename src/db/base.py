"""
Database connection management supporting both SQLite and PostgreSQL
"""

import abc
import asyncio
import json
import os
import re
import secrets
import time
import uuid
import warnings
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

import aiosqlite
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


class ConnectionPool:
    """Simple connection pool for SQLite (reused from original implementation)"""

    def __init__(self, db_path: str, pool_size: int, timeout: float):
        self.db_path = db_path
        self.pool_size = pool_size
        self.timeout = timeout
        self._pool: asyncio.Queue[aiosqlite.Connection] = asyncio.Queue(maxsize=pool_size)
        self._created_connections = 0

    async def initialize(self):
        """Initialize the connection pool"""
        if self.pool_size > 0:
            first_conn = await self._create_connection()
            await self._pool.put(first_conn)

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
        
        if self.db_path != ":memory:":
            try:
                await conn.execute("PRAGMA journal_mode = WAL")
            except Exception as e:
                logger.warning(f"Failed to set WAL mode: {e}")

            await conn.execute("PRAGMA wal_autocheckpoint = 10000")
            await conn.execute("PRAGMA journal_size_limit = 67108864")
            
            actual_timeout = max(busy_timeout_ms, 60000)
            await conn.execute(f"PRAGMA busy_timeout = {actual_timeout}")
            await conn.execute("PRAGMA synchronous = NORMAL")
            await conn.execute("PRAGMA mmap_size = 268435456")
        
        await conn.execute("PRAGMA cache_size = -64000")
        await conn.execute("PRAGMA temp_store = MEMORY")
        
        conn.row_factory = aiosqlite.Row
        self._created_connections += 1
        return conn

    async def acquire(self) -> aiosqlite.Connection:
        """Acquire a connection from the pool"""
        try:
            return await asyncio.wait_for(self._pool.get(), timeout=self.timeout)
        except TimeoutError as e:
            logger.error("Timeout waiting for database connection from pool")
            raise DatabaseConnectionError("Database connection pool timeout") from e

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
                await conn.execute("PRAGMA optimize")
            except Exception:
                pass
            await conn.close()
            db_connections_active.dec()


class SQLiteDatabase(DatabaseInterface):
    """Async SQLite database implementation"""

    def __init__(self):
        raw_db_path = os.getenv("TEST_DATABASE_PATH", settings.database_path)
        self.db_path: str = self._resolve_db_path(raw_db_path)
        self._pool: ConnectionPool | None = None

    @staticmethod
    def _resolve_db_path(db_path: str) -> str:
        if db_path == ":memory:":
            return db_path
        if Path(db_path).is_absolute():
            return db_path
        project_root = Path("/app") if Path("/app/migrations").exists() else Path(__file__).parent.parent.parent
        return str((project_root / db_path).resolve())

    async def _apply_migrations(self, conn: aiosqlite.Connection):
        """Apply all migrations to the database (used for proper :memory: initialization)"""
        logger.info("Applying migrations to in-memory database...")
        project_root = Path(__file__).parent.parent.parent
        migrations_dir = project_root / "migrations" / "sqlite"
        
        await conn.execute("CREATE TABLE IF NOT EXISTS _migrations (filename TEXT PRIMARY KEY, applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        applied_rows = await conn.execute_fetchall("SELECT filename FROM _migrations")
        applied = {row[0] for row in applied_rows}
        
        if not migrations_dir.exists():
             logger.warning(f"Migrations directory not found: {migrations_dir}")
             return

        migration_files = sorted([f for f in os.listdir(migrations_dir) if f.endswith(".sql")])
        
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

    async def connect(self) -> None:
        try:
            if self.db_path != ":memory:":
                Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

            self._pool = ConnectionPool(
                db_path=self.db_path, pool_size=settings.database_pool_size, timeout=settings.database_pool_timeout
            )
            await self._pool.initialize()

            logger.info(f"Connected to SQLite database: {self.db_path}")
            db_connections_active.set(settings.database_pool_size)

            # Apply migrations if in-memory
            conn = await self._pool.acquire()
            try:
                if self.db_path == ":memory:":
                    await self._apply_migrations(conn)
            finally:
                await self._pool.release(conn)

        except Exception as e:
            logger.error(f"Failed to connect to SQLite: {e}")
            raise DatabaseConnectionError(str(e)) from e

    async def disconnect(self) -> None:
        if self._pool:
            await self._pool.close_all()
            self._pool = None
            logger.info("SQLite connection pool closed")

    def _convert_query(self, query: str) -> str:
        """Convert PostgreSQL query syntax to SQLite"""
        query = re.sub(r"\$\d+", "?", query)
        query = re.sub(r"\bNOW\(\)", "datetime('now')", query, flags=re.IGNORECASE)
        query = re.sub(r"\s+=\s+true\b", " = 1", query, flags=re.IGNORECASE)
        # Handle "returning" clauses if simple enough, or warn
        return re.sub(r"\s+=\s+false\b", " = 0", query, flags=re.IGNORECASE)

    async def execute(self, query: str, *args) -> str:
        if not self._pool:
            raise RuntimeError("Database connection pool not initialized")
        query = self._convert_query(query)
        
        start_wait = time.time()
        conn = await self._pool.acquire()
        wait_duration_ms = int((time.time() - start_wait) * 1000)
        
        max_retries = 10
        retry_delay = 0.2
        
        try:
            for attempt in range(max_retries):
                start_exec = time.time()
                try:
                    await conn.execute("BEGIN IMMEDIATE")
                    async with conn.execute(query, args) as cursor:
                        await conn.commit()
                        exec_duration_ms = int((time.time() - start_exec) * 1000)
                        db_query_duration_seconds.labels(operation="execute").observe(exec_duration_ms / 1000.0)
                        return f"Rows affected: {cursor.rowcount}"
                except Exception as e:
                    # Rollback
                    try:
                        await conn.rollback()
                    except Exception:
                        pass
                    
                    error_str = str(e).lower()
                    if ("locked" in error_str) and attempt < max_retries - 1:
                        actual_delay = retry_delay * (2 ** attempt) + (secrets.SystemRandom().random() * 0.5)
                        await asyncio.sleep(actual_delay)
                        continue
                    
                    if "integrityerror" in str(type(e)).lower():
                        raise DatabaseIntegrityError(str(e)) from e
                    raise DatabaseError(str(e)) from e
            raise DatabaseError("Failed to execute query after retries")
        finally:
            await self._pool.release(conn)

    async def fetch(self, query: str, *args) -> list[dict[str, Any]]:
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
                
                if query.strip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
                    await conn.commit()
                    
                return [dict(row) for row in rows]
        except Exception as e:
             logger.error(f"Fetch error: {e}, Query: {query[:100]}")
             raise DatabaseError(str(e)) from e
        finally:
            await self._pool.release(conn)

    async def fetchone(self, query: str, *args) -> dict[str, Any] | None:
        if not self._pool:
            raise RuntimeError("Database connection pool not initialized")
        query = self._convert_query(query)
        conn = await self._pool.acquire()
        start_time = time.time()
        try:
            async with conn.execute(query, args) as cursor:
                row = await cursor.fetchone()
                if query.strip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
                    await conn.commit()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Fetchone error: {e}, Query: {query[:100]}")
            raise DatabaseError(str(e)) from e
        finally:
            await self._pool.release(conn)

    async def fetchval(self, query: str, *args) -> Any:
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
            raise DatabaseError(str(e)) from e
        finally:
            await self._pool.release(conn)

    async def health_check(self) -> DatabaseHealth:
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
        try:
            start = time.time()
            await self.fetchval("SELECT 1")
            latency_ms = int((time.time() - start) * 1000)
            db_size_mb = 0.0
            if Path(self.db_path).exists():
                db_size_mb = round(Path(self.db_path).stat().st_size / (1024 * 1024), 2)
            return DatabaseHealth(
                status="up",
                latency_ms=latency_ms,
                database="sqlite",
                path=self.db_path,
                size_mb=db_size_mb,
                pool_size=settings.database_pool_size,
                error=None,
            )
        except Exception as e:
            return DatabaseHealth(
                status="down",
                error=str(e),
                latency_ms=None,
                database="sqlite",
                path=self.db_path,
                size_mb=0.0,
                pool_size=settings.database_pool_size,
            )


class PostgresDatabase(DatabaseInterface):
    """Async PostgreSQL database implementation using asyncpg"""

    def __init__(self):
        self._pool: asyncpg.Pool | None = None
        
    async def connect(self) -> None:
        try:
            self._pool = await asyncpg.create_pool(
                user=settings.postgres_user,
                password=settings.postgres_password,
                host=settings.postgres_host,
                port=settings.postgres_port,
                database=settings.postgres_database,
                min_size=settings.postgres_pool_min_size,
                max_size=settings.postgres_pool_max_size,
            )
            logger.info(
                f"Connected to PostgreSQL database at {settings.postgres_host}:{settings.postgres_port}/{settings.postgres_database}"
            )
            db_connections_active.set(settings.postgres_pool_min_size)
            
            # Use jsonb codec via basic configuration if needed, but asyncpg handles it often automatically.
            # However, for UUIDs, asyncpg returns UUID objects, which fits our needs.
            
        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL: {e}")
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


def get_db() -> DatabaseInterface:
    """Factory function to get the appropriate database instance"""
    if settings.database_type == "postgresql":
        return PostgresDatabase()
    return SQLiteDatabase()


# Global database instance
db = get_db()


async def init_db():
    """Initialize database connection (called on startup)"""
    await db.connect()


async def close_db():
    """Close database connection (called on shutdown)"""
    await db.disconnect()
