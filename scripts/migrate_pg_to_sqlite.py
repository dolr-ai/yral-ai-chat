#!/usr/bin/env python3
"""
Migrate data from PostgreSQL dump to SQLite
Parses PostgreSQL COPY format and inserts into SQLite

Usage:
    python scripts/migrate_pg_to_sqlite.py [--pg-dump PATH] [--sqlite-db PATH]
"""
import sqlite3
import json
import re
import argparse
from pathlib import Path
from datetime import datetime

# Default paths
DEFAULT_PG_DUMP = "/root/yral-ai-chat/yral_chat_backup_20251203.sql"
DEFAULT_SQLITE_DB = "/root/yral-ai-chat/data/yral_chat.db"
DEFAULT_SCHEMA = "/root/yral-ai-chat/migrations/sqlite/001_init_schema.sql"


def parse_copy_block(content: str, table_name: str) -> list:
    """Parse a PostgreSQL COPY block and extract rows"""
    # Find the COPY block for this table
    pattern = rf"COPY public\.{table_name} \(([^)]+)\) FROM stdin;(.*?)\\."
    match = re.search(pattern, content, re.DOTALL)
    
    if not match:
        print(f"  No data found for table: {table_name}")
        return [], []
    
    columns = [col.strip() for col in match.group(1).split(',')]
    data_block = match.group(2).strip()
    
    if not data_block:
        print(f"  Empty data block for table: {table_name}")
        return columns, []
    
    rows = []
    for line in data_block.split('\n'):
        if not line.strip():
            continue
        
        # PostgreSQL COPY uses tab as delimiter
        # Handle escaped characters
        values = []
        for val in line.split('\t'):
            if val == '\\N':
                values.append(None)
            elif val == 't':
                values.append(1)  # SQLite boolean
            elif val == 'f':
                values.append(0)  # SQLite boolean
            else:
                # Unescape PostgreSQL escape sequences
                val = val.replace('\\n', '\n')
                val = val.replace('\\t', '\t')
                val = val.replace('\\\\', '\\')
                values.append(val)
        
        rows.append(values)
    
    return columns, rows


def create_database(db_path: str, schema_path: str) -> sqlite3.Connection:
    """Create SQLite database with schema"""
    # Ensure directory exists
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    
    # Remove existing database if exists
    if Path(db_path).exists():
        print(f"Removing existing database: {db_path}")
        Path(db_path).unlink()
    
    conn = sqlite3.connect(db_path)
    
    # Enable WAL mode for Litestream
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    
    # Load and execute schema
    print(f"Loading schema from: {schema_path}")
    with open(schema_path, 'r') as f:
        schema = f.read()
    
    conn.executescript(schema)
    conn.commit()
    
    print("Schema created successfully")
    return conn


def migrate_influencers(conn: sqlite3.Connection, columns: list, rows: list):
    """Migrate ai_influencers data"""
    print(f"  Migrating {len(rows)} influencers...")
    
    cursor = conn.cursor()
    
    for row in rows:
        row_dict = dict(zip(columns, row))
        
        cursor.execute("""
            INSERT INTO ai_influencers (
                id, name, display_name, avatar_url, description, 
                category, system_instructions, personality_traits,
                is_active, created_at, updated_at, metadata, initial_greeting
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            row_dict['id'],
            row_dict['name'],
            row_dict['display_name'],
            row_dict['avatar_url'],
            row_dict['description'],
            row_dict['category'],
            row_dict['system_instructions'],
            row_dict['personality_traits'],
            row_dict['is_active'],
            row_dict['created_at'],
            row_dict['updated_at'],
            row_dict['metadata'],
            row_dict.get('initial_greeting')
        ))
    
    conn.commit()
    print(f"  ✓ Migrated {len(rows)} influencers")


def migrate_conversations(conn: sqlite3.Connection, columns: list, rows: list):
    """Migrate conversations data"""
    print(f"  Migrating {len(rows)} conversations...")
    
    cursor = conn.cursor()
    
    for row in rows:
        row_dict = dict(zip(columns, row))
        
        cursor.execute("""
            INSERT INTO conversations (
                id, user_id, influencer_id, created_at, updated_at, metadata
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            row_dict['id'],
            row_dict['user_id'],
            row_dict['influencer_id'],
            row_dict['created_at'],
            row_dict['updated_at'],
            row_dict['metadata']
        ))
    
    conn.commit()
    print(f"  ✓ Migrated {len(rows)} conversations")


def migrate_messages(conn: sqlite3.Connection, columns: list, rows: list):
    """Migrate messages data"""
    print(f"  Migrating {len(rows)} messages...")
    
    cursor = conn.cursor()
    
    for row in rows:
        row_dict = dict(zip(columns, row))
        
        cursor.execute("""
            INSERT INTO messages (
                id, conversation_id, role, content, message_type,
                media_urls, audio_url, audio_duration_seconds,
                token_count, created_at, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            row_dict['id'],
            row_dict['conversation_id'],
            row_dict['role'],
            row_dict['content'],
            row_dict['message_type'],
            row_dict['media_urls'],
            row_dict['audio_url'],
            row_dict['audio_duration_seconds'],
            row_dict['token_count'],
            row_dict['created_at'],
            row_dict['metadata']
        ))
    
    conn.commit()
    print(f"  ✓ Migrated {len(rows)} messages")


def verify_migration(conn: sqlite3.Connection):
    """Verify data was migrated correctly"""
    cursor = conn.cursor()
    
    print("\n📊 Migration Summary:")
    
    cursor.execute("SELECT COUNT(*) FROM ai_influencers")
    count = cursor.fetchone()[0]
    print(f"  ai_influencers: {count} rows")
    
    cursor.execute("SELECT COUNT(*) FROM conversations")
    count = cursor.fetchone()[0]
    print(f"  conversations: {count} rows")
    
    cursor.execute("SELECT COUNT(*) FROM messages")
    count = cursor.fetchone()[0]
    print(f"  messages: {count} rows")
    
    # Show influencer names
    cursor.execute("SELECT name, display_name FROM ai_influencers")
    print("\n  Influencers:")
    for row in cursor.fetchall():
        print(f"    - {row[0]}: {row[1]}")


def main():
    parser = argparse.ArgumentParser(description='Migrate PostgreSQL dump to SQLite')
    parser.add_argument('--pg-dump', default=DEFAULT_PG_DUMP, help='Path to PostgreSQL dump file')
    parser.add_argument('--sqlite-db', default=DEFAULT_SQLITE_DB, help='Path to SQLite database')
    parser.add_argument('--schema', default=DEFAULT_SCHEMA, help='Path to SQLite schema file')
    args = parser.parse_args()
    
    print("=" * 60)
    print("PostgreSQL to SQLite Migration")
    print("=" * 60)
    print(f"\nSource: {args.pg_dump}")
    print(f"Target: {args.sqlite_db}")
    print(f"Schema: {args.schema}")
    print()
    
    # Read PostgreSQL dump
    print("📖 Reading PostgreSQL dump...")
    with open(args.pg_dump, 'r', encoding='utf-8') as f:
        pg_content = f.read()
    
    # Create SQLite database
    print("\n🔧 Creating SQLite database...")
    conn = create_database(args.sqlite_db, args.schema)
    
    # Parse and migrate each table
    print("\n📦 Migrating data...")
    
    # Migrate ai_influencers
    print("\n[1/3] ai_influencers:")
    columns, rows = parse_copy_block(pg_content, 'ai_influencers')
    if rows:
        migrate_influencers(conn, columns, rows)
    
    # Migrate conversations
    print("\n[2/3] conversations:")
    columns, rows = parse_copy_block(pg_content, 'conversations')
    if rows:
        migrate_conversations(conn, columns, rows)
    
    # Migrate messages
    print("\n[3/3] messages:")
    columns, rows = parse_copy_block(pg_content, 'messages')
    if rows:
        migrate_messages(conn, columns, rows)
    
    # Verify migration
    verify_migration(conn)
    
    # Close connection
    conn.close()
    
    print("\n" + "=" * 60)
    print("✅ Migration complete!")
    print("=" * 60)
    print(f"\nSQLite database: {args.sqlite_db}")
    print("\nNext steps:")
    print("  1. Configure Litestream for S3 backups")
    print("  2. Start the application with: uvicorn src.main:app")
    print("  3. Test endpoints: curl http://localhost:8000/health")


if __name__ == "__main__":
    main()

