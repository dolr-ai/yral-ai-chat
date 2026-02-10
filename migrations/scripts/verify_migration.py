"""
Verify SQLite to PostgreSQL migration.
Checks row counts and validates ID preservation.
"""
import asyncio
import json
import sys
from pathlib import Path

import aiosqlite
import asyncpg
from deepdiff import DeepDiff
from loguru import logger

sys.path.append(str(Path(__file__).parent.parent))
from src.config import settings

SQLITE_DB_PATH = "./data/yral_chat_staging.db"
PG_DSN = f"postgresql://{settings.postgres_user}:{settings.postgres_password}@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_database}"
TABLES = ["ai_influencers", "conversations", "messages"]


async def get_sqlite_conn():
    """Connect to SQLite database."""
    conn = await aiosqlite.connect(SQLITE_DB_PATH)
    conn.row_factory = aiosqlite.Row
    return conn


async def get_postgres_pool():
    """Create PostgreSQL connection pool."""
    return await asyncpg.create_pool(dsn=PG_DSN)


async def verify_counts(sqlite_conn, pg_pool):
    """Verify row counts match between SQLite and PostgreSQL."""
    async with pg_pool.acquire() as pg_conn:
        for table in TABLES:
            # Get counts
            async with sqlite_conn.execute(f"SELECT COUNT(*) FROM {table}") as cursor:
                sqlite_count = (await cursor.fetchone())[0]
            
            pg_count = await pg_conn.fetchval(f"SELECT COUNT(*) FROM {table}")
            
            # Log results
            logger.info(f"Table {table}: SQLite={sqlite_count}, Postgres={pg_count}")
            
            if sqlite_count == pg_count:
                logger.info(f"MATCH in table {table}.")
            else:
                logger.error(f"MISMATCH in table {table}!")


def parse_json_if_string(value):
    """Parse JSON string to dict/list if it's a string."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except:
            return value
    return value


async def verify_samples(sqlite_conn, pg_pool):
    """Verify sample records can be found by original IDs."""
    logger.info("Verifying data samples...")
    
    async with pg_pool.acquire() as pg_conn:
        # Verify influencer by ID
        async with sqlite_conn.execute("SELECT * FROM ai_influencers LIMIT 1") as cursor:
            sqlite_row = dict(await cursor.fetchone())
        
        logger.info(f"Checking influencer {sqlite_row['name']} with ID {sqlite_row['id']}")
        pg_row = await pg_conn.fetchrow("SELECT * FROM ai_influencers WHERE id = $1", sqlite_row['id'])
        
        if not pg_row:
            logger.error(f"Influencer not found in PG with ID {sqlite_row['id']}")
            return
        
        pg_row = dict(pg_row)
        
        # Parse JSON fields for comparison
        for field in ['personality_traits', 'metadata', 'suggested_messages']:
            if field in sqlite_row:
                sqlite_row[field] = parse_json_if_string(sqlite_row[field])
            if field in pg_row:
                pg_row[field] = parse_json_if_string(pg_row[field])
        
        # Compare (ignoring timestamps and fields that may differ)
        diff = DeepDiff(
            sqlite_row, pg_row, 
            ignore_order=True,
            exclude_paths=["root['created_at']", "root['updated_at']", "root['is_active']", "root['is_nsfw']"]
        )
        
        if not diff:
            logger.info("Influencer sample match.")
        else:
            logger.warning(f"Influencer sample diff: {diff}")
        
        # Verify message by ID
        async with sqlite_conn.execute("SELECT * FROM messages ORDER BY created_at DESC LIMIT 1") as cursor:
            sqlite_msg = dict(await cursor.fetchone())
        
        logger.info(f"Checking message {sqlite_msg['id']}")
        pg_msg = await pg_conn.fetchrow("SELECT * FROM messages WHERE id = $1", sqlite_msg['id'])
        
        if not pg_msg:
            logger.error(f"Message not found in PG with ID {sqlite_msg['id']}")
            return
        
        pg_msg = dict(pg_msg)
        
        # Parse JSON and boolean fields
        for field in ['metadata', 'media_urls']:
            if field in sqlite_msg:
                sqlite_msg[field] = parse_json_if_string(sqlite_msg[field])
            if field in pg_msg:
                pg_msg[field] = parse_json_if_string(pg_msg[field])
        
        sqlite_msg['is_read'] = bool(sqlite_msg.get('is_read', 0))
        
        # Compare
        diff = DeepDiff(
            sqlite_msg, pg_msg,
            ignore_order=True,
            exclude_paths=["root['created_at']", "root['updated_at']", "root['client_message_id']"]
        )
        
        if not diff:
            logger.info("Message sample match.")
        else:
            logger.info(f"Message sample comparison complete. Diff: {diff}")


async def main():
    """Main verification orchestrator."""
    sqlite_conn = await get_sqlite_conn()
    pg_pool = await get_postgres_pool()
    
    try:
        await verify_counts(sqlite_conn, pg_pool)
        await verify_samples(sqlite_conn, pg_pool)
    finally:
        await sqlite_conn.close()
        await pg_pool.close()


if __name__ == "__main__":
    asyncio.run(main())
