#!/usr/bin/env python3
"""
Migrate data from SQLite to PostgreSQL
Usage: python3 scripts/migrate_sqlite_to_postgres.py
"""
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import execute_values, Json

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from src.config import settings

def connect_sqlite(db_path: str) -> sqlite3.Connection:
    if not Path(db_path).exists():
        print(f"Error: SQLite database not found at {db_path}")
        sys.exit(1)
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def connect_postgres(dsn: str):
    try:
        conn = psycopg2.connect(dsn)
        return conn
    except Exception as e:
        print(f"Error connecting to PostgreSQL: {e}")
        sys.exit(1)

def parse_datetime(dt_str: str | None) -> datetime | None:
    if not dt_str:
        return None
    try:
        # Try various formats
        if "T" in dt_str:
            return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return datetime.now() # Fallback

def migrate_table(sqlite_conn: sqlite3.Connection, pg_conn, table_name: str, transform_func):
    print(f"Migrating {table_name}...")
    
    # Get all rows from SQLite
    cursor = sqlite_conn.cursor()
    cursor.execute(f"SELECT * FROM {table_name}")
    rows = cursor.fetchall()
    
    if not rows:
        print(f"  No rows in {table_name}, skipping.")
        return

    print(f"  Found {len(rows)} rows.")
    
    # Transform rows
    transformed_data = []
    columns = rows[0].keys()
    
    for row in rows:
        row_dict = dict(row)
        transformed = transform_func(row_dict)
        transformed_data.append(transformed)
    
    # Prepare Insert
    # Assuming transformed_data is list of dicts with same keys
    pg_cursor = pg_conn.cursor()
    
    # Generate INSERT query dynamically
    cols_order = list(transformed_data[0].keys())
    cols_str = ", ".join(cols_order)
    # execute_values handles the tuple generation
    
    query = f"INSERT INTO {table_name} ({cols_str}) VALUES %s ON CONFLICT (id) DO NOTHING"
    
    values = [[item[col] for col in cols_order] for item in transformed_data]
    
    execute_values(pg_cursor, query, values)
    pg_conn.commit()
    print(f"  Successfully inserted {len(values)} rows into {table_name}")

def transform_influencer(row: dict) -> dict:
    # JSON fields
    for field in ['personality_traits', 'suggested_messages', 'metadata']:
        if isinstance(row.get(field), str):
            try:
                # Ensure valid JSON
                val = json.loads(row[field])
                row[field] = json.dumps(val) # Send as string for JSONB implicit cast
            except:
                row[field] = '{}' if field != 'suggested_messages' else '[]'
    
    # Timestamps
    row['created_at'] = parse_datetime(row.get('created_at'))
    row['updated_at'] = parse_datetime(row.get('updated_at'))
    
    return row

def transform_conversation(row: dict) -> dict:
    # JSON fields
    for field in ['metadata']:
        if isinstance(row.get(field), str):
            try:
                row[field] = json.dumps(json.loads(row[field]))
            except:
                row[field] = '{}'
    
    # Timestamps
    row['created_at'] = parse_datetime(row.get('created_at'))
    row['updated_at'] = parse_datetime(row.get('updated_at'))
    
    return row

def transform_message(row: dict) -> dict:
    # JSON fields
    for field in ['media_urls', 'metadata']:
        if isinstance(row.get(field), str):
            try:
                row[field] = json.dumps(json.loads(row[field]))
            except:
                row[field] = '[]' if field == 'media_urls' else '{}'
    
    # Timestamps
    row['created_at'] = parse_datetime(row.get('created_at'))
    
    return row

def init_postgres_schema(pg_conn):
    print("Initializing PostgreSQL schema...")
    schema_path = Path(__file__).parent.parent / "migrations" / "postgres" / "001_init_schema.sql"
    with open(schema_path, "r") as f:
        sql = f.read()
    
    cursor = pg_conn.cursor()
    cursor.execute(sql)
    pg_conn.commit()
    print("Schema initialized.")

def main():
    # Config
    # If explicit paths provided via env, use them, otherwise defaults
    sqlite_db_path = os.environ.get("SQLITE_DB_PATH", "data/yral_chat.db")
    postgres_url = os.environ.get("DATABASE_URL")
    
    if not postgres_url:
        # Try constructing from components
        user = os.environ.get("POSTGRES_USER", "postgres")
        password = os.environ.get("POSTGRES_PASSWORD", "postgres")
        host = "localhost" # Default for script running locally against mapped port
        port = "5432"
        db = os.environ.get("POSTGRES_DB", "yral_chat")
        postgres_url = f"postgresql://{user}:{password}@{host}:{port}/{db}"

    print(f"Source SQLite: {sqlite_db_path}")
    print(f"Dest Postgres: {postgres_url}") # Careful printing password in real logs
    
    # Connect
    sqlite_conn = connect_sqlite(sqlite_db_path)
    pg_conn = connect_postgres(postgres_url)
    
    # Init Schema
    init_postgres_schema(pg_conn)
    
    try:
        # Migrate in order
        migrate_table(sqlite_conn, pg_conn, "ai_influencers", transform_influencer)
        migrate_table(sqlite_conn, pg_conn, "conversations", transform_conversation)
        migrate_table(sqlite_conn, pg_conn, "messages", transform_message)
        
        print("\nMigration Complete! ✅")
        
    except Exception as e:
        print(f"\nMigration Failed ❌: {e}")
        pg_conn.rollback()
        sys.exit(1)
    finally:
        sqlite_conn.close()
        pg_conn.close()

if __name__ == "__main__":
    main()
