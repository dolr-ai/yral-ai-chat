#!/usr/bin/env python3
"""
Database migration runner for SQLite
Runs migration SQL files in order
"""
import os
import sqlite3
import sys
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

        migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))

        if not migration_files:
            return

        for migration_file in migration_files:
            _execute_migration(conn, migration_file)

        conn.execute("PRAGMA journal_mode = WAL")
        conn.commit()

    except Exception:
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    run_migrations()

