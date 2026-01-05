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
    DB_PATH = Path(os.getenv("DATABASE_PATH", "/app/data/yral_chat.db"))
else:
    PROJECT_ROOT = Path(__file__).parent.parent
    DB_PATH = Path(os.getenv("DATABASE_PATH", str(PROJECT_ROOT / "data" / "yral_chat.db")))

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
    cursor = conn.execute(f"PRAGMA table_info({table_name})")
    return any(row[1] == column_name for row in cursor.fetchall())


def _get_column_type(conn: sqlite3.Connection, table_name: str, column_name: str) -> str | None:
    """Get the type of a column, or None if it doesn't exist."""
    cursor = conn.execute(f"PRAGMA table_info({table_name})")
    for row in cursor.fetchall():
        if row[1] == column_name:
            return row[2].upper()  # Return uppercase type (e.g., 'TEXT', 'INTEGER')
    return None


def _handle_migration_007(conn: sqlite3.Connection, migration_file: Path) -> bool:
    """Handle migration 007: Add suggested_messages column if needed"""
    if (migration_file.name == "007_add_initial_suggested_messages.sql" and
            _table_exists(conn, "ai_influencers") and
            not _column_exists(conn, "ai_influencers", "suggested_messages")):
        conn.execute(
            "ALTER TABLE ai_influencers "
            "ADD COLUMN suggested_messages TEXT DEFAULT '[]'"
        )
        conn.commit()
        return True
    return False


def _handle_migration_012(conn: sqlite3.Connection, migration_file: Path) -> bool:
    """Handle migration 012: Convert is_active from INTEGER to TEXT enum"""
    if (migration_file.name == "012_convert_is_active_to_enum.sql" and
            _table_exists(conn, "ai_influencers")):
        is_active_type = _get_column_type(conn, "ai_influencers", "is_active")
        status_exists = _column_exists(conn, "ai_influencers", "status")
        
        if is_active_type == "TEXT":
            return True
        
        if status_exists and is_active_type == "INTEGER":
            sql = migration_file.read_text(encoding="utf-8")
            sql_lines = sql.split("\n")
            sql_lines = [
                line for line in sql_lines
                if not (
                    "ALTER TABLE" in line.upper() and
                    "ADD COLUMN" in line.upper() and
                    "status" in line.lower() and
                    "TEXT" in line.upper()
                )
            ]
            sql = "\n".join(sql_lines)
        else:
            sql = migration_file.read_text(encoding="utf-8")
        
        conn.executescript(sql)
        conn.commit()
        return True
    return False


def _execute_migration(conn: sqlite3.Connection, migration_file: Path) -> None:
    """Execute a regular migration file"""
    sql = migration_file.read_text(encoding="utf-8")
    conn.executescript(sql)
    conn.commit()


def _verify_influencers(conn: sqlite3.Connection) -> None:
    """Verify influencer IDs and display their status"""
    try:
        cursor = conn.execute(
            "SELECT name, id, is_active FROM ai_influencers "
            "ORDER BY CASE is_active "
            "  WHEN 'active' THEN 1 "
            "  WHEN 'coming_soon' THEN 2 "
            "  WHEN 'discontinued' THEN 3 "
            "END, name"
        )
        influencers = cursor.fetchall()
        if influencers:
            for _name, _id_val, is_active in influencers:
                if not isinstance(is_active, int | bool):
                    status_map = {
                        "active": "ACTIVE",
                        "coming_soon": "COMING SOON",
                        "discontinued": "DISCONTINUED"
                    }
                    status_map.get(is_active, f"UNKNOWN: {is_active}")
    except sqlite3.OperationalError:
        pass  # Table doesn't exist yet


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
            if _handle_migration_007(conn, migration_file):
                continue
            if _handle_migration_012(conn, migration_file):
                continue
            
            _execute_migration(conn, migration_file)

        conn.execute("PRAGMA journal_mode = WAL")
        conn.commit()

        cursor = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
        cursor.fetchone()[0]

        _verify_influencers(conn)

    except Exception:
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":

    run_migrations()

