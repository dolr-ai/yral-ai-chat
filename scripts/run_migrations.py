#!/usr/bin/env python3
"""
Database migration runner for SQLite.
Ensures safe schema updates across different environments.
"""
import os
import re
import shutil
import sqlite3
import sys
import time
import traceback
from pathlib import Path
from typing import Optional

# --- Configuration ---
PROJECT_ROOT = Path("/app") if Path("/app/migrations").exists() else Path(__file__).parent.parent
DB_DEFAULT = "data/yral_chat.db"
DB_PATH_RAW = os.getenv("DATABASE_PATH", DB_DEFAULT)
DB_PATH = Path(DB_PATH_RAW).resolve() if Path(DB_PATH_RAW).is_absolute() else (PROJECT_ROOT / DB_PATH_RAW).resolve()
MIGRATIONS_DIR = PROJECT_ROOT / "migrations" / "sqlite"

def _backup_database() -> Optional[Path]:
    """Step 1: Create a safety backup before any changes."""
    if not DB_PATH.exists():
        return None
    
    backup_dir = DB_PATH.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"{DB_PATH.name}_{timestamp}.bak"
    
    print(f"Creating backup: {backup_path}") # noqa: T201
    shutil.copy2(DB_PATH, backup_path)
    return backup_path

def _split_sql(sql: str) -> list[str]:
    """Helper: Split SQL into statements while respecting semicolons in strings."""
    pattern = r"'[^']*'|\"[^\"]*\"|[^'\";]+|;"
    matches = re.findall(pattern, sql)
    
    statements, current = [], []
    for m in matches:
        if m == ";":
            stmt = "".join(current).strip()
            if stmt: statements.append(stmt)
            current = []
        else:
            current.append(m)
            
    final = "".join(current).strip()
    if final: statements.append(final)
    return statements

def _execute_migration(conn: sqlite3.Connection, migration_file: Path) -> None:
    """Step 2: Execute migration with atomic transaction and conflict recovery."""
    sql_text = migration_file.read_text(encoding="utf-8")
    
    try:
        # Strategy A: Run as single script (Atomic)
        conn.executescript(sql_text)
        conn.commit()
    except sqlite3.OperationalError as e:
        error_msg = str(e).lower()
        if "duplicate column name" in error_msg or "already exists" in error_msg:
            # Strategy B: Recovery - Run statement-by-statement and skip applied ones
            print(f"  [RECOVERY] Already applied detected, syncing statement-by-statement...") # noqa: T201
            try: conn.rollback()
            except sqlite3.OperationalError: pass
            
            for cmd in _split_sql(sql_text):
                try:
                    conn.execute(cmd)
                except sqlite3.OperationalError as inner_e:
                    if "duplicate column name" in str(inner_e).lower() or "already exists" in str(inner_e).lower():
                        continue # Safely skip
                    raise
            conn.commit()
        else:
            try: conn.rollback()
            except sqlite3.OperationalError: pass
            raise

def run_migrations():
    """Main Orchestrator"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    _backup_database()

    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        
        # Step 3: Initialize tracking table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS _migrations (
                filename TEXT PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Step 4: Map applied files
        applied = {row[0] for row in conn.execute("SELECT filename FROM _migrations")}

        # Step 5: Process pending migrations in order
        for migration in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if migration.name in applied:
                print(f"Skipping {migration.name} (already recorded)") # noqa: T201
                continue

            print(f"Applying {migration.name}...") # noqa: T201
            _execute_migration(conn, migration)
            conn.execute("INSERT INTO _migrations (filename) VALUES (?)", (migration.name,))
            conn.commit()

        # Step 6: Finalize Database State
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
