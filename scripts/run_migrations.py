#!/usr/bin/env python3
"""
Database migration runner for SQLite
Runs migration SQL files in order
"""
import os
import sqlite3
import sys
from pathlib import Path

# Get paths - works both in Docker and locally
# In Docker: /app is the working directory
# Locally: script is in scripts/ directory
if Path("/app").exists():
    # Running in Docker
    PROJECT_ROOT = Path("/app")
    DB_PATH = Path(os.getenv("DATABASE_PATH", "/app/data/yral_chat.db"))
else:
    # Running locally
    PROJECT_ROOT = Path(__file__).parent.parent
    DB_PATH = PROJECT_ROOT / "data" / "yral_chat.db"

MIGRATIONS_DIR = PROJECT_ROOT / "migrations" / "sqlite"


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    """Check if a table exists in the current database."""
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
        (table_name,),
    )
    return cursor.fetchone() is not None


def _column_exists(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    """Check if a column exists on a given table."""
    # table_name is controlled by our code (no user input), so using it
    # directly in the PRAGMA statement is safe here.
    cursor = conn.execute(f"PRAGMA table_info({table_name})")
    return any(row[1] == column_name for row in cursor.fetchall())


def run_migrations():
    """Run all migration files in order"""
    # Ensure data directory exists
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Connect to database
    conn = sqlite3.connect(str(DB_PATH))

    try:
        # Enable foreign keys
        conn.execute("PRAGMA foreign_keys = ON")

        # Get list of migration files
        migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))

        if not migration_files:
            return


        for migration_file in migration_files:

            # Backwards-compatible handling for adding suggested_messages column:
            # older SQLite versions don't support "ADD COLUMN IF NOT EXISTS",
            # so we add the column from Python if it doesn't exist yet.
            if (
                migration_file.name == "007_add_initial_suggested_messages.sql"
                and _table_exists(conn, "ai_influencers")
                and not _column_exists(conn, "ai_influencers", "suggested_messages")
            ):
                    conn.execute(
                        "ALTER TABLE ai_influencers "
                        "ADD COLUMN suggested_messages TEXT DEFAULT '[]'"
                    )
                    conn.commit()

            with migration_file.open(encoding="utf-8") as f:
                sql = f.read()

            # Execute migration
            cursor = conn.executescript(sql)

            # Check if any rows were affected (for UPDATE/INSERT statements)
            if cursor.rowcount >= 0:
                pass

            conn.commit()


        # Enable WAL mode for better concurrency
        conn.execute("PRAGMA journal_mode = WAL")
        conn.commit()


        # Show database info
        cursor = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
        cursor.fetchone()[0]

        # Verify influencer IDs (if ai_influencers table exists)
        try:
            cursor = conn.execute(
                "SELECT name, id, is_active FROM ai_influencers "
                "ORDER BY is_active DESC, name"
            )
            influencers = cursor.fetchall()
            if influencers:
                for _name, _id_val, _is_active in influencers:
                    pass
        except sqlite3.OperationalError:
            pass  # Table doesn't exist yet

    except Exception:
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":

    run_migrations()

