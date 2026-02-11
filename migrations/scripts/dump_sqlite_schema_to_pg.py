"""
Generate PostgreSQL schema from SQLite database.
Preserves TEXT IDs and maps types appropriately.
"""
import sqlite3
from pathlib import Path

DB_PATH = "./data/yral_chat_staging.db"
OUTPUT_FILE = "migrations/postgresql/SCHEMA_FROM_SQLITE.sql"

# Columns that should be JSONB in PostgreSQL
JSON_COLUMNS = {
    "ai_influencers": ["personality_traits", "suggested_messages", "metadata"],
    "conversations": ["metadata"],
    "messages": ["media_urls", "metadata"]
}

# Tables to migrate (in order due to foreign keys)
TABLES = ["ai_influencers", "conversations", "messages"]


def get_pg_type(table: str, col_name: str, sqlite_type: str) -> str:
    """Map SQLite column type to PostgreSQL type with defaults."""
    col_lower = col_name.lower()
    
    # JSON columns
    if col_name in JSON_COLUMNS.get(table, []):
        default = "'[]'" if "messages" in col_name or "media" in col_name else "'{}'"
        return f"JSONB DEFAULT {default}"
    
    # Special columns
    if col_lower in ['created_at', 'updated_at']:
        return "TIMESTAMP WITH TIME ZONE DEFAULT NOW()"
    
    if col_lower == 'is_active':
        return "TEXT DEFAULT 'active'"
    
    if col_lower in ['is_read', 'is_nsfw']:
        return "BOOLEAN DEFAULT FALSE"
    
    # Standard type mapping
    sqlite_upper = sqlite_type.upper()
    if "INT" in sqlite_upper:
        return "INTEGER"
    if "BOOL" in sqlite_upper:
        return "BOOLEAN"
    
    return "TEXT"


def generate_table_ddl(cursor, table: str) -> str:
    """Generate CREATE TABLE statement for a table."""
    cursor.execute(f"PRAGMA table_info({table})")
    columns = cursor.fetchall()
    
    lines = [f"-- Table: {table}", f"CREATE TABLE IF NOT EXISTS {table} ("]
    
    # Column definitions
    col_defs = []
    for cid, name, col_type, notnull, dflt_value, pk in columns:
        pg_type = get_pg_type(table, name, col_type)
        
        if name == "id" and pk:
            col_def = f"    {name} TEXT PRIMARY KEY"
        else:
            col_def = f"    {name} {pg_type}"
            if notnull and not pk:
                col_def += " NOT NULL"
        
        col_defs.append(col_def)
    
    # Foreign keys
    cursor.execute(f"PRAGMA foreign_key_list({table})")
    for _, _, ref_table, from_col, to_col, _, on_delete, _ in cursor.fetchall():
        fk = f"    FOREIGN KEY ({from_col}) REFERENCES {ref_table}({to_col})"
        if on_delete:
            fk += f" ON DELETE {on_delete}"
        col_defs.append(fk)
    
    lines.append(",\n".join(col_defs))
    lines.append(");\n")
    
    return "\n".join(lines)


def generate_indexes(cursor, table: str) -> str:
    """Generate CREATE INDEX statements for a table."""
    cursor.execute(
        f"SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name='{table}'"
    )
    
    indexes = []
    for (sql,) in cursor.fetchall():
        if sql and "sqlite_autoindex" not in sql:
            indexes.append(f"{sql};")
    
    return "\n".join(indexes) if indexes else ""


def generate_schema():
    """Main function to generate PostgreSQL schema from SQLite."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    with open(OUTPUT_FILE, "w") as f:
        f.write("-- Generated from SQLite Schema\n\n")
        f.write('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";\n\n')
        
        for table in TABLES:
            # Table definition
            f.write(generate_table_ddl(cursor, table))
            f.write("\n")
            
            # Indexes
            indexes = generate_indexes(cursor, table)
            if indexes:
                f.write(indexes)
                f.write("\n\n")
    
    conn.close()
    print(f"Schema dumped to {OUTPUT_FILE}")


if __name__ == "__main__":
    generate_schema()
