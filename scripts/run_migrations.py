#!/usr/bin/env python3
"""
Database migration runner for SQLite
Runs migration SQL files in order
"""
import os
import sqlite3
import sys
import traceback
from pathlib import Path

if Path("/app/migrations").exists():
    PROJECT_ROOT = Path("/app")
    default_db_path = "data/yral_chat.db"
else:
    PROJECT_ROOT = Path(__file__).parent.parent
    default_db_path = "data/yral_chat.db"

# Get database path from env or use default relative path
db_path_env = os.getenv("DATABASE_PATH", default_db_path)
# Resolve relative paths to absolute paths
DB_PATH = Path(db_path_env) if Path(db_path_env).is_absolute() else (PROJECT_ROOT / db_path_env).resolve()

MIGRATIONS_DIR = PROJECT_ROOT / "migrations" / "sqlite"


def _execute_migration(conn: sqlite3.Connection, migration_file: Path) -> None:
    """Execute a regular migration file"""
    sql = migration_file.read_text(encoding="utf-8")
    conn.executescript(sql)
    conn.commit()


def run_migrations():
    """Run all migration files in order"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(DB_PATH))

    try:
        conn.execute("PRAGMA foreign_keys = ON")
        
        # internal tracking table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS _migrations (
                filename TEXT PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Check for legacy schema state (specifically if 005 was already applied)
        # We check if the table is empty, and if the column 'is_nsfw' exists in ai_influencers
        cursor = conn.execute("SELECT count(*) FROM _migrations")
        if cursor.fetchone()[0] == 0:
            try:
                # Check if ai_influencers table exists
                cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ai_influencers'")
                if cursor.fetchone():
                    # Check if is_nsfw column exists
                    cursor = conn.execute("PRAGMA table_info(ai_influencers)")
                    columns = [info[1] for info in cursor.fetchall()]
                    if "is_nsfw" in columns:
                        print("Detected existing schema with is_nsfw column. Marking 001-005 as applied.")  # noqa: T201
                        existing = [
                            "001_init_schema.sql",
                            "002_seed_influencers.sql",
                            "003_updates.sql",
                            "004_dashboard_views.sql",
                            "005_add_nsfw_flag.sql"
                        ]
                        for f in existing:
                            conn.execute("INSERT OR IGNORE INTO _migrations (filename) VALUES (?)", (f,))
                        conn.commit()
            except Exception as e:
                print(f"Warning during legacy schema check: {e}")  # noqa: T201

        # Get set of applied migrations
        applied_migrations = {row[0] for row in conn.execute("SELECT filename FROM _migrations")}

        migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))

        if not migration_files:
            return

        for migration_file in migration_files:
            if migration_file.name in applied_migrations:
                print(f"Skipping {migration_file.name} (already applied)")  # noqa: T201
                continue

            print(f"Applying {migration_file.name}...")  # noqa: T201
            _execute_migration(conn, migration_file)
            
            # Record it
            conn.execute("INSERT INTO _migrations (filename) VALUES (?)", (migration_file.name,))
            conn.commit()

        conn.execute("PRAGMA journal_mode = WAL")
        conn.commit()

    except Exception:
        traceback.print_exc()
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    run_migrations()

