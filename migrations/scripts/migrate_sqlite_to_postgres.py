"""
Migrate data from SQLite to PostgreSQL.
Preserves original string IDs and handles JSON serialization.
"""
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite
import asyncpg
from dateutil import parser
from loguru import logger

sys.path.append(str(Path(__file__).parent.parent))
from src.config import settings

SQLITE_DB_PATH = "./data/yral_chat_staging.db"
PG_DSN = f"postgresql://{settings.postgres_user}:{settings.postgres_password}@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_database}"


# Utility Functions
def parse_datetime(dt_str: str | None) -> datetime | None:
    """Parse ISO datetime string to datetime object with UTC timezone."""
    if not dt_str:
        return None
    try:
        dt = parser.parse(dt_str)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        logger.warning(f"Failed to parse datetime: {dt_str}")
        return None


def parse_json(json_str: str | None, default: Any = None) -> Any:
    """Parse JSON string, return default on failure."""
    if not json_str:
        return default
    try:
        return json.loads(json_str)
    except Exception:
        return default


def to_json(data: Any) -> str:
    """Serialize to JSON string for PostgreSQL JSONB."""
    return json.dumps(data)


# Database Connections
async def get_sqlite_conn():
    """Connect to SQLite database."""
    if not Path(SQLITE_DB_PATH).exists():
        logger.error(f"SQLite database not found at {SQLITE_DB_PATH}")
        sys.exit(1)
    conn = await aiosqlite.connect(SQLITE_DB_PATH)
    conn.row_factory = aiosqlite.Row
    return conn


async def get_postgres_pool():
    """Create PostgreSQL connection pool."""
    try:
        return await asyncpg.create_pool(dsn=PG_DSN)
    except Exception as e:
        logger.error(f"Failed to connect to PostgreSQL: {e}")
        sys.exit(1)


# Migration Functions
async def migrate_influencers(sqlite_conn, pg_pool):
    """Migrate AI influencers with original IDs."""
    logger.info("Migrating Influencers...")
    
    async with sqlite_conn.execute("SELECT * FROM ai_influencers") as cursor:
        rows = await cursor.fetchall()
    
    logger.info(f"Found {len(rows)} influencers to migrate.")
    
    query = """
        INSERT INTO ai_influencers (
            id, name, display_name, avatar_url, description, category,
            system_instructions, personality_traits, initial_greeting,
            suggested_messages, is_active, created_at, updated_at,
            metadata, is_nsfw, parent_principal_id, source, status
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18)
        ON CONFLICT (id) DO UPDATE SET
            name = EXCLUDED.name,
            display_name = EXCLUDED.display_name,
            avatar_url = EXCLUDED.avatar_url,
            description = EXCLUDED.description,
            category = EXCLUDED.category,
            system_instructions = EXCLUDED.system_instructions,
            personality_traits = EXCLUDED.personality_traits,
            initial_greeting = EXCLUDED.initial_greeting,
            suggested_messages = EXCLUDED.suggested_messages,
            is_active = EXCLUDED.is_active,
            updated_at = EXCLUDED.updated_at,
            metadata = EXCLUDED.metadata,
            is_nsfw = EXCLUDED.is_nsfw,
            parent_principal_id = EXCLUDED.parent_principal_id,
            source = EXCLUDED.source,
            status = EXCLUDED.status;
    """
    
    async with pg_pool.acquire() as pg_conn:
        for row in rows:
            data = dict(row)
            
            try:
                await pg_conn.execute(
                    query,
                    data['id'],
                    data['name'],
                    data['display_name'],
                    data['avatar_url'],
                    data['description'],
                    data['category'],
                    data['system_instructions'],
                    to_json(parse_json(data['personality_traits'], {})),
                    data['initial_greeting'],
                    to_json(parse_json(data['suggested_messages'], [])),
                    data['is_active'],
                    parse_datetime(data['created_at']),
                    parse_datetime(data.get('updated_at')),
                    to_json(parse_json(data.get('metadata'), {})),
                    bool(data.get('is_nsfw', 0)),
                    data.get('parent_principal_id'),
                    data.get('source'),
                    data.get('status')
                )
            except asyncpg.UniqueViolationError:
                logger.warning(f"Duplicate influencer: {data['name']}")
    
    logger.info("Influencers migration complete.")


async def migrate_conversations(sqlite_conn, pg_pool):
    """Migrate conversations with original IDs."""
    logger.info("Migrating Conversations...")
    
    async with sqlite_conn.execute("SELECT * FROM conversations") as cursor:
        rows = await cursor.fetchall()
    
    logger.info(f"Found {len(rows)} conversations to migrate.")
    
    query = """
        INSERT INTO conversations (
            id, user_id, influencer_id, created_at, updated_at, metadata
        ) VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (id) DO NOTHING;
    """
    
    async with pg_pool.acquire() as pg_conn:
        for row in rows:
            data = dict(row)
            
            try:
                await pg_conn.execute(
                    query,
                    data['id'],
                    data['user_id'],
                    data['influencer_id'],
                    parse_datetime(data['created_at']),
                    parse_datetime(data.get('updated_at')),
                    to_json(parse_json(data.get('metadata'), {}))
                )
            except asyncpg.ForeignKeyViolationError:
                logger.warning(f"Skipping conversation {data['id']} - missing influencer {data['influencer_id']}")
            except asyncpg.DataError as e:
                logger.error(f"DataError for conversation {data['id']}: {e}")
    
    logger.info("Conversations migration complete.")


async def migrate_messages(sqlite_conn, pg_pool):
    """Migrate messages with original IDs."""
    logger.info("Migrating Messages...")
    
    async with sqlite_conn.execute("SELECT * FROM messages") as cursor:
        rows = await cursor.fetchall()
    
    logger.info(f"Found {len(rows)} messages to migrate.")
    
    query = """
        INSERT INTO messages (
            id, conversation_id, role, content, message_type,
            media_urls, audio_url, audio_duration_seconds,
            token_count, created_at, metadata,
            client_message_id, is_read, status
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
        ON CONFLICT (id) DO NOTHING
    """
    
    async with pg_pool.acquire() as pg_conn:
        for row in rows:
            data = dict(row)
            
            try:
                await pg_conn.execute(
                    query,
                    data['id'],
                    data['conversation_id'],
                    data['role'],
                    data['content'],
                    data['message_type'],
                    to_json(parse_json(data.get('media_urls'), [])),
                    data.get('audio_url'),
                    data.get('audio_duration_seconds'),
                    data.get('token_count'),
                    parse_datetime(data['created_at']),
                    to_json(parse_json(data.get('metadata'), {})),
                    data.get('client_message_id'),
                    bool(data.get('is_read', 0)),
                    data.get('status', 'delivered')
                )
            except asyncpg.ForeignKeyViolationError:
                logger.warning(f"Skipping message {data['id']} - missing conversation {data['conversation_id']}")
            except Exception as e:
                logger.error(f"Error migrating message {data['id']}: {e}")
    
    logger.info("Messages migration complete.")


async def main():
    """Main migration orchestrator."""
    logger.info(f"Starting migration from {SQLITE_DB_PATH} to PostgreSQL...")
    
    sqlite_conn = await get_sqlite_conn()
    pg_pool = await get_postgres_pool()
    
    try:
        await migrate_influencers(sqlite_conn, pg_pool)
        await migrate_conversations(sqlite_conn, pg_pool)
        await migrate_messages(sqlite_conn, pg_pool)
        logger.info("Migration finished successfully!")
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise
    finally:
        await sqlite_conn.close()
        await pg_pool.close()


if __name__ == "__main__":
    asyncio.run(main())
