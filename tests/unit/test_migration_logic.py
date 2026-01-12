import sys
import json
from datetime import datetime
from pathlib import Path

# Add scripts to path to import migration logic
sys.path.append(str(Path(__file__).parent.parent.parent / "scripts"))

from migrate_sqlite_to_postgres import transform_influencer, transform_conversation, transform_message, parse_datetime

def test_parse_datetime():
    assert parse_datetime(None) is None
    dt = parse_datetime("2024-01-01 10:00:00")
    assert dt.year == 2024
    assert dt.hour == 10
    
    # ISO compatibility
    dt_iso = parse_datetime("2024-01-01T10:00:00")
    assert dt_iso.year == 2024

def test_transform_influencer():
    row = {
        "personality_traits": json.dumps({"witty": True}),
        "suggested_messages": json.dumps(["Hi"]),
        "metadata": "{}",
        "created_at": "2024-01-01 10:00:00",
        "updated_at": None,
        "is_active": "active"
    }
    
    transformed = transform_influencer(row)
    
    # Check JSON string formatted correctly (it stays string for psycopg2 usually, but here we expect string? 
    # Wait, the script converts it back to json.dumps string.
    # Postgres asyncpg/psycopg2 might prefer string for JSONB if we don't use Json adapter explicitly for everything.
    # The script implementation: row[field] = json.dumps(val)
    
    assert transformed["personality_traits"] == '{"witty": true}'
    assert transformed["suggested_messages"] == '["Hi"]'
    assert isinstance(transformed["created_at"], datetime)
    assert transformed["updated_at"] is None

def test_transform_bad_json():
    # Test resilience against bad data
    row = {
        "personality_traits": "INVALID JSON",
        "suggested_messages": None,
        "metadata": None,
        "created_at": "invalid date",
        "updated_at": None
    }
    
    transformed = transform_influencer(row)
    
    assert transformed["personality_traits"] == "{}" # Fallback
    assert transformed["suggested_messages"] is None # Preserves None/NULL
    assert isinstance(transformed["created_at"], datetime) # Fallback to Now
