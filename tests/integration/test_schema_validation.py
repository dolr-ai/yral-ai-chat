"""
Schema Validation Tests

Validates that production/staging databases have the correct schema structure.
This ensures all required tables, columns, indexes, and triggers exist.

Usage:
    # Test against default database (from settings)
    pytest tests/integration/test_schema_validation.py -v
    
    # Test against specific database path
    DATABASE_PATH=/path/to/prod.db pytest tests/integration/test_schema_validation.py -v
    
    # Test against staging database
    DATABASE_PATH=/path/to/staging.db pytest tests/integration/test_schema_validation.py -v
    
    # Or use pytest marker
    pytest tests/integration/test_schema_validation.py -v --db-path /path/to/db.db
"""
import os
import sqlite3
from pathlib import Path

import pytest

from src.config import settings

# Expected schema definition
EXPECTED_TABLES = {
    "ai_influencers": {
        "columns": {
            "id": "TEXT",
            "name": "TEXT",
            "display_name": "TEXT",
            "avatar_url": "TEXT",
            "description": "TEXT",
            "category": "TEXT",
            "system_instructions": "TEXT",
            "personality_traits": "TEXT",
            "initial_greeting": "TEXT",
            "suggested_messages": "TEXT",
            "is_active": "TEXT",  # Must be TEXT, not INTEGER
            "created_at": "TEXT",
            "updated_at": "TEXT",
            "metadata": "TEXT",
        },
        "required_columns": [
            "id",
            "name",
            "display_name",
            "system_instructions",
            "is_active",
        ],
        "indexes": [
            "idx_influencers_name",
            "idx_influencers_category",
            "idx_influencers_active",
        ],
    },
    "conversations": {
        "columns": {
            "id": "TEXT",
            "user_id": "TEXT",
            "influencer_id": "TEXT",
            "created_at": "TEXT",
            "updated_at": "TEXT",
            "metadata": "TEXT",
        },
        "required_columns": [
            "id",
            "user_id",
            "influencer_id",
        ],
        "indexes": [
            "idx_conversations_user_id",
            "idx_conversations_influencer_id",
            "idx_unique_user_influencer",
            "idx_conversations_updated_at",
        ],
    },
    "messages": {
        "columns": {
            "id": "TEXT",
            "conversation_id": "TEXT",
            "role": "TEXT",
            "content": "TEXT",
            "message_type": "TEXT",
            "media_urls": "TEXT",
            "audio_url": "TEXT",
            "audio_duration_seconds": "INTEGER",
            "token_count": "INTEGER",
            "created_at": "TEXT",
            "metadata": "TEXT",
        },
        "required_columns": [
            "id",
            "conversation_id",
            "role",
            "message_type",
        ],
        "indexes": [
            "idx_messages_conversation_id",
            "idx_messages_role",
            "idx_messages_created_at",
            "idx_messages_conversation_created",
        ],
    },
}

EXPECTED_TRIGGERS = [
    "trigger_update_conversation_timestamp",
    "trigger_update_influencer_timestamp",
    "trigger_validate_influencer_status",
    "trigger_validate_influencer_status_update",
]


def get_db_connection():
    """Get database connection - supports DATABASE_PATH env var override"""
    # Allow override via environment variable for testing prod/staging
    db_path_str = os.getenv("DATABASE_PATH") or settings.database_path
    db_path = Path(db_path_str)
    
    if not db_path.exists():
        pytest.skip(f"Database not found at {db_path}")
    
    conn = sqlite3.connect(str(db_path))
    # Enable foreign keys (required for SQLite, matches application behavior)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_table_info(conn: sqlite3.Connection, table_name: str) -> dict:
    """Get column information for a table"""
    cursor = conn.execute(f"PRAGMA table_info({table_name})")
    columns = {}
    for row in cursor.fetchall():
        col_name = row[1]
        col_type = row[2].upper()
        columns[col_name] = col_type
    return columns


def get_indexes(conn: sqlite3.Connection, table_name: str) -> list:
    """Get all indexes for a table"""
    cursor = conn.execute(
        f"SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='{table_name}'"
    )
    return [row[0] for row in cursor.fetchall()]


def get_triggers(conn: sqlite3.Connection) -> list:
    """Get all triggers"""
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'")
    return [row[0] for row in cursor.fetchall()]


def test_all_required_tables_exist():
    """Test that all required tables exist"""
    conn = get_db_connection()
    try:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        existing_tables = {row[0] for row in cursor.fetchall()}
        expected_tables = set(EXPECTED_TABLES.keys())
        
        missing_tables = expected_tables - existing_tables
        assert not missing_tables, f"Missing tables: {missing_tables}"
    finally:
        conn.close()


def test_table_columns_exist():
    """Test that all required columns exist in each table"""
    conn = get_db_connection()
    try:
        for table_name, table_spec in EXPECTED_TABLES.items():
            actual_columns = get_table_info(conn, table_name)
            expected_columns = table_spec["columns"]
            required_columns = table_spec["required_columns"]
            
            # Check required columns exist
            missing_required = set(required_columns) - set(actual_columns.keys())
            assert not missing_required, (
                f"Table '{table_name}' missing required columns: {missing_required}"
            )
            
            # Check all expected columns exist
            missing_expected = set(expected_columns.keys()) - set(actual_columns.keys())
            assert not missing_expected, (
                f"Table '{table_name}' missing expected columns: {missing_expected}"
            )
    finally:
        conn.close()


def test_column_types_are_correct():
    """Test that column types match expected types"""
    conn = get_db_connection()
    try:
        for table_name, table_spec in EXPECTED_TABLES.items():
            actual_columns = get_table_info(conn, table_name)
            expected_columns = table_spec["columns"]
            
            for col_name, expected_type in expected_columns.items():
                if col_name not in actual_columns:
                    continue  # Already checked in test_table_columns_exist
                
                actual_type = actual_columns[col_name]
                # SQLite type checking is flexible, but we check for critical ones
                if expected_type == "TEXT" and actual_type not in ("TEXT", "VARCHAR"):
                    pytest.fail(
                        f"Table '{table_name}' column '{col_name}' should be TEXT, got {actual_type}"
                    )
                elif expected_type == "INTEGER" and actual_type != "INTEGER":
                    pytest.fail(
                        f"Table '{table_name}' column '{col_name}' should be INTEGER, got {actual_type}"
                    )
    finally:
        conn.close()


def test_is_active_is_text_not_integer():
    """Critical test: is_active must be TEXT, not INTEGER"""
    conn = get_db_connection()
    try:
        columns = get_table_info(conn, "ai_influencers")
        assert "is_active" in columns, "is_active column missing"
        assert columns["is_active"] == "TEXT", (
            f"is_active must be TEXT (enum), got {columns['is_active']}. "
            "This should be TEXT with values: 'active', 'coming_soon', 'discontinued'"
        )
    finally:
        conn.close()


def test_required_indexes_exist():
    """Test that all required indexes exist"""
    conn = get_db_connection()
    try:
        for table_name, table_spec in EXPECTED_TABLES.items():
            actual_indexes = get_indexes(conn, table_name)
            expected_indexes = table_spec["indexes"]
            
            missing_indexes = set(expected_indexes) - set(actual_indexes)
            assert not missing_indexes, (
                f"Table '{table_name}' missing indexes: {missing_indexes}"
            )
    finally:
        conn.close()


def test_required_triggers_exist():
    """Test that all required triggers exist"""
    conn = get_db_connection()
    try:
        actual_triggers = get_triggers(conn)
        missing_triggers = set(EXPECTED_TRIGGERS) - set(actual_triggers)
        assert not missing_triggers, f"Missing triggers: {missing_triggers}"
    finally:
        conn.close()


def test_foreign_keys_are_enabled():
    """Test that foreign keys are enabled"""
    conn = get_db_connection()
    try:
        cursor = conn.execute("PRAGMA foreign_keys")
        result = cursor.fetchone()
        assert result[0] == 1, "Foreign keys are not enabled. Run: PRAGMA foreign_keys = ON"
    finally:
        conn.close()


def test_ai_influencers_has_suggested_messages():
    """Test that suggested_messages column exists"""
    conn = get_db_connection()
    try:
        columns = get_table_info(conn, "ai_influencers")
        assert "suggested_messages" in columns, (
            "suggested_messages column missing. "
            "This column should exist in the schema."
        )
        assert columns["suggested_messages"] == "TEXT", (
            f"suggested_messages should be TEXT, got {columns['suggested_messages']}"
        )
    finally:
        conn.close()


def test_schema_summary(capsys):
    """Print a summary of the database schema (informational test)"""
    conn = get_db_connection()
    try:
        print("\n" + "=" * 60)
        print("DATABASE SCHEMA SUMMARY")
        print("=" * 60)
        
        for table_name in EXPECTED_TABLES:
            columns = get_table_info(conn, table_name)
            indexes = get_indexes(conn, table_name)
            print(f"\n📊 Table: {table_name}")
            print(f"   Columns: {len(columns)}")
            print(f"   Indexes: {len(indexes)}")
            print(f"   Required columns: {', '.join(EXPECTED_TABLES[table_name]['required_columns'])}")
        
        triggers = get_triggers(conn)
        print(f"\n⚙️  Triggers: {len(triggers)}")
        print(f"   {', '.join(triggers)}")
        
        # Check foreign keys
        cursor = conn.execute("PRAGMA foreign_keys")
        fk_enabled = cursor.fetchone()[0]
        print(f"\n🔗 Foreign Keys: {'✅ Enabled' if fk_enabled else '❌ Disabled'}")
        
        print("\n" + "=" * 60)
    finally:
        conn.close()
