# Database Architecture

## Overview

The application uses **SQLite** as the primary database with **Litestream** for continuous backup and replication to S3-compatible storage.

## Database Choice Rationale

### Why SQLite?

- **Simplicity**: No separate database server to manage
- **Performance**: Fast for read-heavy workloads with connection pooling
- **Reliability**: ACID compliant, crash-safe
- **Portability**: Single file database
- **Cost-effective**: No separate database hosting costs

### Limitations

- **Concurrency**: Limited concurrent writes (mitigated with connection pooling)
- **Scale**: Best for small to medium workloads
- **Network**: File-based (not network-distributed)

**Migration Path**: PostgreSQL recommended for high-concurrency production use

## Schema Design

### Entity Relationship Diagram

```
┌─────────────────────┐
│   ai_influencers    │
│ ─────────────────── │
│ • id (PK)          │
│ • name             │
│ • display_name     │
│ • avatar_url       │
│ • description      │
│ • category         │
│ • system_instr...  │
│ • personality...   │
│ • is_active        │
│ • created_at       │
└──────────┬──────────┘
           │
           │ 1:N
           │
┌──────────▼──────────┐
│   conversations     │
│ ─────────────────── │
│ • id (PK)          │
│ • user_id          │
│ • influencer_id(FK)│
│ • created_at       │
│ • updated_at       │
└──────────┬──────────┘
           │
           │ 1:N
           │
┌──────────▼──────────┐
│     messages        │
│ ─────────────────── │
│ • id (PK)          │
│ • conversation_id(FK)│
│ • role             │
│ • content          │
│ • message_type     │
│ • media_urls       │
│ • audio_url        │
│ • audio_duration   │
│ • token_count      │
│ • created_at       │
└─────────────────────┘
```

## Tables

### ai_influencers

Stores AI persona definitions and configurations.

```sql
CREATE TABLE ai_influencers (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    avatar_url TEXT,
    description TEXT,
    category TEXT,
    system_instructions TEXT NOT NULL,
    personality_traits TEXT,
    is_active TEXT CHECK(is_active IN ('active', 'coming soon', 'discontinued')) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Indexes:**
- `idx_influencers_name` on `name`
- `idx_influencers_active` on `is_active`

**Usage:**
- Read-heavy (rarely modified)
- Cached in application memory
- Queried for discovery and conversation creation

### conversations

Links users with AI influencers. One conversation per user-influencer pair.

```sql
CREATE TABLE conversations (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    influencer_id TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (influencer_id) REFERENCES ai_influencers(id) ON DELETE CASCADE,
    UNIQUE(user_id, influencer_id)
);
```

**Indexes:**
- `idx_conversations_user` on `user_id`
- `idx_conversations_influencer` on `influencer_id`
- `idx_conversations_updated` on `updated_at`

**Usage:**
- Frequent reads for conversation lists
- Infrequent writes (conversation creation)
- Updated timestamp on new messages

### messages

Individual chat messages in conversations.

```sql
CREATE TABLE messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT,
    message_type TEXT NOT NULL CHECK (message_type IN ('TEXT', 'IMAGE', 'MULTIMODAL', 'AUDIO')),
    media_urls TEXT,
    audio_url TEXT,
    audio_duration_seconds INTEGER,
    token_count INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);
```

**Indexes:**
- `idx_messages_conversation` on `conversation_id`
- `idx_messages_created` on `created_at`
- `idx_messages_role` on `role`

**Usage:**
- High write volume (every message exchange)
- Frequent reads for message history
- Paginated queries (LIMIT/OFFSET)

## Connection Pooling

### Configuration

```python
pool_size = 10          # Maximum concurrent connections
timeout = 30            # Connection timeout (seconds)
max_overflow = 5        # Additional connections when pool exhausted
```

### Pool Management

- **Lifecycle**: Connections created on-demand, reused
- **Health Checks**: Periodic validation queries
- **Cleanup**: Automatic connection release
- **Stats**: Pool size, active connections exposed in health endpoint

### Best Practices

1. **Always use context managers** for transactions
2. **Release connections promptly** after use
3. **Avoid long-running transactions**
4. **Monitor pool exhaustion** via metrics

## Migrations

### Migration System

Custom SQL-based migrations in `migrations/sqlite/`:

```
migrations/
└── sqlite/
    ├── 001_init_schema.sql      # Initial schema
    └── 002_seed_influencers.sql # Seed data
```

### Running Migrations

```bash
python scripts/run_migrations.py
```

### Creating Migrations

1. Create new SQL file: `NNN_description.sql`
2. Write migration SQL
3. Run migration script
4. Commit to version control

## Backup & Replication (Litestream)

### How Litestream Works

1. **Continuous Replication**: Real-time SQLite WAL streaming
2. **S3 Upload**: Incremental backups to S3-compatible storage
3. **Point-in-Time Recovery**: Restore to any point in time
4. **Automatic**: Runs as background process

### Configuration

Location: `config/litestream.yml`

```yaml
dbs:
  - path: /path/to/yral_chat.db
    replicas:
      - url: s3://bucket-name/db-backup
        access-key-id: $LITESTREAM_ACCESS_KEY_ID
        secret-access-key: $LITESTREAM_SECRET_ACCESS_KEY
```

### Recovery

```bash
# Restore from backup
litestream restore -o /path/to/yral_chat.db s3://bucket/db-backup

# Restore to specific point in time
litestream restore -o /path/to/yral_chat.db -timestamp 2024-01-01T10:00:00Z s3://bucket/db-backup
```

## Query Patterns

### Common Queries

**List User Conversations:**
```sql
SELECT c.*, i.name, i.display_name, i.avatar_url,
       COUNT(m.id) as message_count
FROM conversations c
JOIN ai_influencers i ON c.influencer_id = i.id
LEFT JOIN messages m ON c.id = m.conversation_id
WHERE c.user_id = ?
GROUP BY c.id
ORDER BY c.updated_at DESC
LIMIT ? OFFSET ?
```

**Get Conversation Messages:**
```sql
SELECT id, role, content, message_type, media_urls,
       audio_url, audio_duration_seconds, token_count, created_at
FROM messages
WHERE conversation_id = ?
ORDER BY created_at DESC
LIMIT ? OFFSET ?
```

**Count Active Influencers:**
```sql
SELECT COUNT(*) FROM ai_influencers WHERE is_active = 'active'
```

## Performance Optimization

### Indexes

All foreign keys and frequently queried columns are indexed for fast lookups.

### Caching Strategy

- **Influencer Data**: Cached in memory (10 min TTL)
- **Conversation Lists**: Not cached (real-time data)
- **Message History**: Not cached (frequent updates)

### Pagination

Always use `LIMIT` and `OFFSET` for large result sets:
- Conversations: Default 20, max 100
- Messages: Default 50, max 200

### Vacuum

Periodic VACUUM operations to reclaim space:
```sql
VACUUM;
```

## Monitoring

### Health Checks

```python
# Check database connectivity
await db.fetchval("SELECT 1")

# Get pool stats
pool_size = db.pool_size
active_connections = pool_size - db.pool_free
```

### Metrics

- Total conversations
- Total messages
- Active influencers
- Connection pool usage
- Query latency

## Data Integrity

### Foreign Key Constraints

Enabled to maintain referential integrity:
```sql
PRAGMA foreign_keys = ON;
```

### Cascading Deletes

- Deleting conversation → deletes all messages
- Deleting influencer → deletes all conversations

### Unique Constraints

- One conversation per user-influencer pair
- Unique influencer names

## Scaling Considerations

### When to Migrate to PostgreSQL

Consider PostgreSQL when:
- Concurrent writes exceed 50/second
- Database size exceeds 50GB
- Need multi-master replication
- Require advanced features (full-text search, JSON queries)

### Migration Strategy

1. Export SQLite data to SQL dump
2. Transform schema for PostgreSQL
3. Import data into PostgreSQL
4. Update connection string
5. Test thoroughly
6. Deploy with minimal downtime

### Read Replicas

SQLite supports read-only replicas via Litestream or file copying. For write-heavy workloads, PostgreSQL is recommended.
