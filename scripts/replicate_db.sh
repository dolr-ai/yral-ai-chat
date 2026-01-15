#!/bin/sh
set -e

# Configuration
SOURCE_DB="${SOURCE_DB:-/app/data/yral_chat.db}"
REPLICA_DB="${REPLICA_DB:-/app/data-replica/yral_chat.db}"
SYNC_INTERVAL="${SYNC_INTERVAL:-30}"

echo "Starting database replication..."
echo "Source: $SOURCE_DB"
echo "Target: $REPLICA_DB"
echo "Interval: ${SYNC_INTERVAL}s"

# Ensure target directory exists
mkdir -p "$(dirname "$REPLICA_DB")"

# Replication loop
while true; do
    if [ -f "$SOURCE_DB" ]; then
        # Use SQLite's online backup API for safe, hot backup
        # This blocks writes for a very short duration (milliseconds for small DBs)
        # much safer and faster than cp for active databases
        sqlite3 "$SOURCE_DB" ".backup '$REPLICA_DB'"
        
        # Verify the replica exists and has size
        if [ -s "$REPLICA_DB" ]; then
            echo "$(date -Iseconds) - Replicated successfully ($(du -h "$REPLICA_DB" | cut -f1))"
        else
             echo "$(date -Iseconds) - Error: Replica created but empty"
        fi
    else
        echo "$(date -Iseconds) - Waiting for source database..."
    fi
    
    sleep "$SYNC_INTERVAL"
done
