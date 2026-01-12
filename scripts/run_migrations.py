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

