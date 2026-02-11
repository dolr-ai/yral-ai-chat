# PostgreSQL Optimization Plan for Yral AI Chat

This document outlines a strategy to optimize the database and application performance during and after the migration to PostgreSQL.

## 1. Database Schema Optimizations (Immediate Win) 🚀

### A. Remove Duplicate Indexes
**Observation:** The current schema contains identical indexes on `messages` table.
- `idx_messages_conversation_created`: `(conversation_id, created_at DESC)`
- `idx_messages_conv_created`: `(conversation_id, created_at DESC)`

**Plan:** Remove generic duplicate indexes.
**Pros:** Faster INSERT/UPDATE operations (less overhead), reduced disk usage.
**Cons:** None.

### B. Add JSONB (GIN) Indexes
**Observation:** Columns like `metadata`, `personality_traits`, and `suggested_messages` are stored as `JSONB` but lack specialized indexes. Filtering by JSON fields (e.g., "Find influencers with 'calm' energy") will force a full table scan.

**Plan:** Add GIN indexes on frequently queried JSON columns.
```sql
CREATE INDEX idx_influencers_metadata ON ai_influencers USING GIN (metadata);
CREATE INDEX idx_messages_metadata ON messages USING GIN (metadata);
```
**Pros:** Extremely fast querying of arbitrary JSON data (tags, flags, extra attributes).
**Cons:** Slower writes (GIN indexes are heavy to maintain).
**Strategy:** Add only on columns we filter by.

### C. Text Search (Full-Text Search)
**Observation:** Searching messages using `LIKE '%term%'` is slow and cannot use standard B-Tree indexes effectively (requires sequential scan).

**Plan:** Add a `TSVECTOR` generated column for message content + `GIN` index.
**Pros:** Instant search results, supports stemming (run = running) and ranking.
**Cons:** Increases storage size.

## 2. Application-Level Optimizations ⚡

### A. Caching Static Data (Influencers)
**Observation:** `ai_influencers` data changes rarely but is read on *every* chat interaction (to get system prompt, personality).
**Plan:** Implement in-memory caching (e.g., `alru_cache` or Redis) for influencer profiles with a TTL (e.g., 5-10 minutes).
**Pros:** Drastically reduces DB reads (by ~50% per message exchange).
**Cons:** Updates to influencers (e.g. changing prompt) take a few minutes to propagate unless cache invalidation is implemented.

### B. Connection Pooling & Pgbouncer
**Observation:** Creating a new connection for every request is expensive. `asyncpg` has a built-in pool, but at scale (multiple app replicas), you might hit Postgres connection limits.
**Plan:**
1. **Short Term:** Tune `POSTGRES_POOL_MIN_SIZE` and `MAX_SIZE` in `config.py` (e.g., 10-20).
2. **Long Term:** Deploy **PgBouncer** in transaction pooling mode.
**Pros:** Supports thousands of concurrent client connections with stable DB performance.
**Cons:** Adds infrastructure complexity.

### C. Estimated Counts
**Observation:** `SELECT COUNT(*) FROM messages` scans the entire table in Postgres (MVCC visibility rules). It becomes very slow as the table grows to millions of rows.
**Plan:** Use estimated counts (from system stats) for admin dashboards where 100% accuracy isn't required.
```sql
SELECT reltuples::bigint FROM pg_class WHERE relname = 'messages';
```
**Pros:** Instant result regardless of table size.
**Cons:** Approximation (might be off by a small percentage until vacuum runs).

## 3. Query Optimizations 🔍

### A. Lateral Joins for "Last N Messages"
**Observation:** Fetching the "last message" for a list of conversations currently uses expensive window functions or N+1 queries.
**Plan:** Use `LATERAL JOIN` which is highly optimized in Postgres for "for-each" type queries.

## Summary of Action Plan

| Phase | Optimization | Effort | Impact | Status |
|-------|--------------|--------|--------|--------|
| **1** | **Fix Duplicate Indexes** | Low | Low (Write Perf) | 🟡 Planned |
| **1** | **Add GIN Indexes** | Low | High (JSON Filter) | 🟡 Planned |
| **2** | **Implement Caching (Influencers)** | Medium | High (Read Perf) | 🟡 Planned |
| **2** | **Connection Pool Tuning** | Low | Medium | 🟡 Planned |
| **3** | **Full-Text Search** | Medium | Medium (Feature) | ⚪ Future |

### Recommendation
Start with **Phase 1** (Schema cleanup and GIN indexes) as part of the migration. Implement **Phase 2** (Caching) immediately after deployment if monitoring shows high read load.
