#!/usr/bin/env python3
"""
Database verification script
Validates SQLite database integrity and checks for expected schema
"""
import os
import sqlite3
import sys
from pathlib import Path

# Expected tables that should exist after migrations
EXPECTED_TABLES = ["ai_influencers", "conversations", "messages"]


def verify_database(db_path: str) -> bool:  # noqa: PLR0911
    """
    Verify database is valid SQLite file and has expected schema
    
    Returns:
        True if database is valid, False otherwise
    """
    db_file = Path(db_path)
    
    if not db_file.exists():
        print(f"ERROR: Database file does not exist at {db_path}")  # noqa: T201
        return False
    
    if db_file.stat().st_size == 0:
        print(f"ERROR: Database file is empty at {db_path}")  # noqa: T201
        return False
    
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        cursor.execute("PRAGMA integrity_check")
        integrity_result = cursor.fetchone()
        if integrity_result[0] != "ok":
            print(f"ERROR: Database integrity check failed: {integrity_result[0]}")  # noqa: T201
            conn.close()
            return False
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        if not tables:
            print("WARNING: Database exists but has no tables. This might be a new database.")  # noqa: T201
            conn.close()
            return False
        
        missing_tables = [table for table in EXPECTED_TABLES if table not in tables]
        if missing_tables:
            print(f"INFO: Database is valid but missing some expected tables: {missing_tables}")  # noqa: T201
            print("      This is expected if migrations haven't run yet.")  # noqa: T201
        
        conn.close()
        tables_str = ", ".join(tables)
        print(f"SUCCESS: Database verification passed. Found {len(tables)} table(s): {tables_str}")  # noqa: T201
        return True
        
    except sqlite3.Error as e:
        print(f"ERROR: Failed to open or verify database: {e}")  # noqa: T201
        return False
    except Exception as e:
        print(f"ERROR: Unexpected error during verification: {e}")  # noqa: T201
        return False


def main():
    """Main entry point"""
    db_path = os.getenv("DATABASE_PATH", "/app/data/yral_chat.db")
    
    if not Path(db_path).is_absolute():
        project_root = Path("/app") if Path("/app/migrations").exists() else Path(__file__).parent.parent
        db_path = str((project_root / db_path).resolve())
    
    print(f"Verifying database at: {db_path}")  # noqa: T201
    
    if verify_database(db_path):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
