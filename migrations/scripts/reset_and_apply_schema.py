"""
Reset PostgreSQL database and apply schema migrations.
Drops existing tables and recreates from migration files.
"""
import asyncio
from pathlib import Path
import asyncpg
from loguru import logger
from src.config import settings




async def reset_and_apply():
    """Drop tables and apply schema migrations."""
    logger.info(f"Connecting to PostgreSQL at {settings.postgres_host}...")
    
    try:
        conn = await asyncpg.connect(
            user=settings.postgres_user,
            password=settings.postgres_password,
            host=settings.postgres_host,
            port=settings.postgres_port,
            database=settings.postgres_database
        )
    except Exception as e:
        logger.error(f"Failed to connect: {e}")
        return

    # Drop existing tables
    logger.warning("Dropping tables...")
    try:
        await conn.execute("""
            DROP TABLE IF EXISTS messages CASCADE;
            DROP TABLE IF EXISTS conversations CASCADE;
            DROP TABLE IF EXISTS ai_influencers CASCADE;
        """)
        logger.info("Tables dropped.")
    except Exception as e:
        logger.error(f"Failed to drop tables: {e}")
        await conn.close()
        return

    # Apply migrations
    migrations_dir = Path("migrations/postgresql")
    files_to_apply = [f.name for f in sorted(migrations_dir.glob("*.sql"))]

    
    logger.info(f"Found {len(files_to_apply)} migration files to apply.")

    for filename in files_to_apply:
        logger.info(f"Applying {filename}...")
        
        try:
            sql = (migrations_dir / filename).read_text()
            await conn.execute(sql)
            logger.info(f"Successfully applied {filename}")
        except Exception as e:
            logger.error(f"Failed to apply {filename}: {e}")
            if "init_schema" in filename.lower():
                logger.critical("Init schema failed! Aborting.")
                await conn.close()
                return

    await conn.close()
    logger.info("Reset and Schema Application Complete.")


if __name__ == "__main__":
    asyncio.run(reset_and_apply())
