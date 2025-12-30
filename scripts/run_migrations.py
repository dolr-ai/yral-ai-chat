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
if os.path.exists("/app/migrations"):
    # Running in Docker
    PROJECT_ROOT = Path("/app")
    DB_PATH = Path(os.getenv("DATABASE_PATH", "/app/data/yral_chat.db"))
else:
    # Running locally
    PROJECT_ROOT = Path(__file__).parent.parent
    # Always check DATABASE_PATH environment variable first
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
    # table_name is controlled by our code (no user input), so using it
    # directly in the PRAGMA statement is safe here.
    cursor = conn.execute(f"PRAGMA table_info({table_name})")
    return any(row[1] == column_name for row in cursor.fetchall())


def _get_column_type(conn: sqlite3.Connection, table_name: str, column_name: str) -> str | None:
    """Get the type of a column, or None if it doesn't exist."""
    # table_name is controlled by our code (no user input), so using it
    # directly in the PRAGMA statement is safe here.
    cursor = conn.execute(f"PRAGMA table_info({table_name})")
    for row in cursor.fetchall():
        if row[1] == column_name:
            return row[2].upper()  # Return uppercase type (e.g., 'TEXT', 'INTEGER')
    return None


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
            print(f"⚠️  No migration files found in {MIGRATIONS_DIR}")
            return

        print(f"📦 Found {len(migration_files)} migration file(s)")

        for migration_file in migration_files:
            print(f"\n🔄 Running {migration_file.name}...")

            # Backwards-compatible handling for adding suggested_messages column:
            # older SQLite versions don't support "ADD COLUMN IF NOT EXISTS",
            # so we add the column from Python if it doesn't exist yet.
            if migration_file.name == "007_add_initial_suggested_messages.sql":
                if _table_exists(conn, "ai_influencers") and not _column_exists(
                    conn, "ai_influencers", "suggested_messages"
                ):
                    conn.execute(
                        "ALTER TABLE ai_influencers "
                        "ADD COLUMN suggested_messages TEXT DEFAULT '[]'"
                    )
                    conn.commit()

            # Handle migration 012 idempotently: Convert is_active from INTEGER to TEXT enum
            if migration_file.name == "012_convert_is_active_to_enum.sql":
                if _table_exists(conn, "ai_influencers"):
                    is_active_type = _get_column_type(conn, "ai_influencers", "is_active")
                    status_exists = _column_exists(conn, "ai_influencers", "status")
                    
                    # If is_active is already TEXT, conversion is complete - skip migration
                    if is_active_type == "TEXT":
                        print("   ⏭️  Migration already applied (is_active is already TEXT)")
                        continue
                    
                    # If status column exists but is_active is still INTEGER, migration partially applied
                    # Modify SQL to skip ADD COLUMN step
                    if status_exists and is_active_type == "INTEGER":
                        print("   ⚠️  Detected partially applied migration, continuing...")
                        with open(migration_file, encoding="utf-8") as f:
                            sql = f.read()
                        # Remove the ADD COLUMN status line (handle various whitespace)
                        # Match: ALTER TABLE ai_influencers ADD COLUMN status TEXT;
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
                        # Normal case: run migration as-is
                        with open(migration_file, encoding="utf-8") as f:
                            sql = f.read()
                    
                    # Execute migration
                    cursor = conn.executescript(sql)
                    
                    # Check if any rows were affected
                    if cursor.rowcount >= 0:
                        print(f"   📊 Rows affected: {cursor.rowcount}")
                    
                    conn.commit()
                    print(f"   ✅ {migration_file.name} completed")
                    continue

            with open(migration_file, encoding="utf-8") as f:
                sql = f.read()

            # Execute migration
            cursor = conn.executescript(sql)

            # Check if any rows were affected (for UPDATE/INSERT statements)
            if cursor.rowcount >= 0:
                print(f"   📊 Rows affected: {cursor.rowcount}")

            conn.commit()

            print(f"   ✅ {migration_file.name} completed")

        # Enable WAL mode for better concurrency
        conn.execute("PRAGMA journal_mode = WAL")
        conn.commit()

        print("\n✅ All migrations completed successfully")

        # Show database info
        cursor = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
        table_count = cursor.fetchone()[0]
        print(f"📊 Database has {table_count} table(s)")

        # Verify influencer IDs (if ai_influencers table exists)
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
                print("\n📋 Current influencer IDs:")
                for name, id_val, is_active in influencers:
                    # Handle both enum string values and legacy boolean values
                    if isinstance(is_active, (int, bool)):
                        status = "✅ ACTIVE" if is_active else "⏸️  INACTIVE"
                    else:
                        status_map = {
                            "active": "✅ ACTIVE",
                            "coming_soon": "⏳ COMING SOON",
                            "discontinued": "⏸️  DISCONTINUED"
                        }
                        status = status_map.get(is_active, f"❓ {is_active}")
                    print(f"   {status} | {name:20} | {id_val}")
        except sqlite3.OperationalError:
            pass  # Table doesn't exist yet

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    print("=" * 60)
    print("🗄️  Database Migration Runner")
    print("=" * 60)
    print(f"Database: {DB_PATH}")
    print(f"Migrations: {MIGRATIONS_DIR}")
    print()

    run_migrations()

