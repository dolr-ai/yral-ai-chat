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
if os.path.exists("/app"):
    # Running in Docker
    PROJECT_ROOT = Path("/app")
    DB_PATH = Path(os.getenv("DATABASE_PATH", "/app/data/yral_chat.db"))
else:
    # Running locally
    PROJECT_ROOT = Path(__file__).parent.parent
    DB_PATH = PROJECT_ROOT / "data" / "yral_chat.db"

MIGRATIONS_DIR = PROJECT_ROOT / "migrations" / "sqlite"


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
            cursor = conn.execute("SELECT name, id, is_active FROM ai_influencers ORDER BY is_active DESC, name")
            influencers = cursor.fetchall()
            if influencers:
                print(f"\n📋 Current influencer IDs:")
                for name, id_val, is_active in influencers:
                    status = "✅ ACTIVE" if is_active else "⏸️  INACTIVE"
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

