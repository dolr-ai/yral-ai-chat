"""
Database connection management using aiosqlite (SQLite)
Configured for use with Litestream for real-time S3 backups
"""
import aiosqlite
import re
import uuid
from typing import Any
from pathlib import Path
from loguru import logger
from src.config import settings


class Database:
    """Async SQLite database connection manager"""
    
    def __init__(self):
        self.db_path: str = settings.database_path
        self._connection: aiosqlite.Connection | None = None
    
    async def connect(self) -> None:
        """Create database connection"""
        try:
            # Ensure directory exists
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            
            self._connection = await aiosqlite.connect(
                self.db_path,
                timeout=30.0
            )
            
            # Enable foreign keys
            await self._connection.execute("PRAGMA foreign_keys = ON")
            # Enable WAL mode for better concurrency (required for Litestream)
            await self._connection.execute("PRAGMA journal_mode = WAL")
            # Sync mode for durability with good performance
            await self._connection.execute("PRAGMA synchronous = NORMAL")
            # Increase cache size for better performance
            await self._connection.execute("PRAGMA cache_size = -64000")  # 64MB
            
            # Use Row factory for dict-like access
            self._connection.row_factory = aiosqlite.Row
            
            logger.info(f"Connected to SQLite database: {self.db_path}")
            
            # Log SQLite version
            async with self._connection.execute("SELECT sqlite_version()") as cursor:
                row = await cursor.fetchone()
                logger.info(f"SQLite version: {row[0]}")
                
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise
    
    async def disconnect(self) -> None:
        """Close database connection"""
        if self._connection:
            await self._connection.close()
            self._connection = None
            logger.info("Database connection closed")
    
    async def execute(self, query: str, *args) -> str:
        """Execute a query without returning results"""
        query = self._convert_query(query)
        try:
            async with self._connection.execute(query, args) as cursor:
                await self._connection.commit()
                return f"Rows affected: {cursor.rowcount}"
        except Exception as e:
            logger.error(f"Execute error: {e}, Query: {query[:100]}")
            raise
    
    async def fetch(self, query: str, *args) -> list[dict[str, Any]]:
        """Fetch multiple rows"""
        query = self._convert_query(query)
        try:
            async with self._connection.execute(query, args) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Fetch error: {e}, Query: {query[:100]}")
            raise
    
    async def fetchone(self, query: str, *args) -> dict[str, Any] | None:
        """Fetch a single row"""
        query = self._convert_query(query)
        try:
            async with self._connection.execute(query, args) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Fetchone error: {e}, Query: {query[:100]}")
            raise
    
    async def fetchval(self, query: str, *args) -> Any:
        """Fetch a single value"""
        query = self._convert_query(query)
        try:
            async with self._connection.execute(query, args) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None
        except Exception as e:
            logger.error(f"Fetchval error: {e}, Query: {query[:100]}")
            raise
    
    def _convert_query(self, query: str) -> str:
        """Convert PostgreSQL query syntax to SQLite"""
        # Convert $1, $2, etc. to ?
        query = re.sub(r'\$\d+', '?', query)
        
        # Convert PostgreSQL NOW() to SQLite datetime('now')
        query = re.sub(r'\bNOW\(\)', "datetime('now')", query, flags=re.IGNORECASE)
        
        # Convert PostgreSQL true/false to SQLite 1/0 in comparisons
        # But be careful not to replace inside strings
        query = re.sub(r'\s+=\s+true\b', ' = 1', query, flags=re.IGNORECASE)
        query = re.sub(r'\s+=\s+false\b', ' = 0', query, flags=re.IGNORECASE)
        
        return query
    
    def generate_uuid(self) -> str:
        """Generate a UUID for use as primary key"""
        return str(uuid.uuid4())
    
    async def health_check(self) -> dict:
        """Check database health"""
        try:
            if not self._connection:
                return {"status": "down", "error": "Connection not initialized"}
            
            import time
            start = time.time()
            
            await self.fetchval("SELECT 1")
            
            latency_ms = int((time.time() - start) * 1000)
            
            # Get database file size
            db_size_mb = 0
            if Path(self.db_path).exists():
                db_size_mb = round(Path(self.db_path).stat().st_size / (1024 * 1024), 2)
            
            return {
                "status": "up",
                "latency_ms": latency_ms,
                "database": "sqlite",
                "path": self.db_path,
                "size_mb": db_size_mb
            }
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return {"status": "down", "error": str(e)}


# Global database instance
db = Database()


async def init_db():
    """Initialize database connection (called on startup)"""
    await db.connect()


async def close_db():
    """Close database connection (called on shutdown)"""
    await db.disconnect()
