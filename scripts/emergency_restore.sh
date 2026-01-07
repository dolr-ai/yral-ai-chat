#!/bin/bash
set -e

# Emergency Restore Script for Litestream
# This script provides manual restore procedures for the database
# Usage: ./scripts/emergency_restore.sh [--timestamp TIMESTAMP] [--force]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

DATABASE_PATH="${DATABASE_PATH:-/app/data/yral_chat.db}"
RESTORE_TIMESTAMP=""
FORCE_RESTORE=false
BACKUP_BEFORE_RESTORE=true

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

while [[ $# -gt 0 ]]; do
    case $1 in
        --timestamp)
            RESTORE_TIMESTAMP="$2"
            shift 2
            ;;
        --force)
            FORCE_RESTORE=true
            shift
            ;;
        --no-backup)
            BACKUP_BEFORE_RESTORE=false
            shift
            ;;
        --help)
            echo "Emergency Restore Script for Litestream"
            echo ""
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --timestamp TIMESTAMP   Restore to specific point in time (ISO format)"
            echo "  --force                 Force restore even if database exists"
            echo "  --no-backup             Skip backing up existing database before restore"
            echo "  --help                  Show this help message"
            echo ""
            echo "Environment Variables:"
            echo "  DATABASE_PATH           Database file path (default: /app/data/yral_chat.db)"
            echo "  LITESTREAM_BUCKET       S3 bucket name"
            echo "  LITESTREAM_ACCESS_KEY_ID   S3 access key"
            echo "  LITESTREAM_SECRET_ACCESS_KEY   S3 secret key"
            echo "  LITESTREAM_ENDPOINT     S3 endpoint URL (optional)"
            echo "  LITESTREAM_REGION       S3 region (optional)"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

verify_environment() {
    local missing_vars=()
    
    if [ -z "$LITESTREAM_BUCKET" ]; then
        missing_vars+=("LITESTREAM_BUCKET")
    fi
    if [ -z "$LITESTREAM_ACCESS_KEY_ID" ]; then
        missing_vars+=("LITESTREAM_ACCESS_KEY_ID")
    fi
    if [ -z "$LITESTREAM_SECRET_ACCESS_KEY" ]; then
        missing_vars+=("LITESTREAM_SECRET_ACCESS_KEY")
    fi
    
    if [ ${#missing_vars[@]} -gt 0 ]; then
        print_error "Missing required environment variables:"
        for var in "${missing_vars[@]}"; do
            echo "  - $var"
        done
        exit 1
    fi
}

check_litestream() {
    if ! command -v litestream &> /dev/null; then
        print_error "Litestream is not installed or not in PATH"
        exit 1
    fi
    print_info "Litestream is installed: $(litestream version 2>&1 | head -n1)"
}

generate_config() {
    local db_filename=$(basename "$DATABASE_PATH")
    local s3_path="yral-ai-chat/$db_filename"
    
    LITESTREAM_CONFIG=$(mktemp /tmp/litestream-restore-XXXXXX.yml)
    cat > "$LITESTREAM_CONFIG" <<EOF
# Litestream Configuration (generated for emergency restore)
dbs:
  - path: $DATABASE_PATH
    replicas:
      - type: s3
        bucket: ${LITESTREAM_BUCKET}
        path: $s3_path
        endpoint: ${LITESTREAM_ENDPOINT:-}
        region: ${LITESTREAM_REGION:-us-east-1}
        access-key-id: ${LITESTREAM_ACCESS_KEY_ID}
        secret-access-key: ${LITESTREAM_SECRET_ACCESS_KEY}
        sync-interval: 10s
        retention: 24h
        retention-check-interval: 1h
        snapshot-interval: 1h
EOF
    print_info "Generated Litestream config: $LITESTREAM_CONFIG"
}

verify_backup() {
    print_info "Checking if backup exists..."
    
    if ! litestream snapshots -config "$LITESTREAM_CONFIG" "$DATABASE_PATH" &>/dev/null; then
        print_warning "Could not verify backup existence"
        return 1
    fi
    
    local snapshot_output=$(litestream snapshots -config "$LITESTREAM_CONFIG" "$DATABASE_PATH" 2>&1)
    if echo "$snapshot_output" | grep -qi "no snapshots"; then
        print_error "No backup found in S3"
        return 1
    fi
    
    print_info "Backup exists in S3"
    return 0
}

backup_existing_db() {
    if [ ! -f "$DATABASE_PATH" ]; then
        return 0
    fi
    
    if [ "$BACKUP_BEFORE_RESTORE" = true ]; then
        local backup_path="${DATABASE_PATH}.backup.$(date +%Y%m%d_%H%M%S)"
        print_info "Backing up existing database to: $backup_path"
        cp "$DATABASE_PATH" "$backup_path"
        print_info "Backup created: $backup_path"
    else
        print_warning "Skipping backup of existing database (--no-backup flag set)"
    fi
}

restore_database() {
    print_info "Starting database restore..."
    
    mkdir -p "$(dirname "$DATABASE_PATH")"
    
    local restore_cmd="litestream restore -config \"$LITESTREAM_CONFIG\" \"$DATABASE_PATH\""
    
    if [ -n "$RESTORE_TIMESTAMP" ]; then
        restore_cmd="$restore_cmd -timestamp \"$RESTORE_TIMESTAMP\""
        print_info "Restoring to timestamp: $RESTORE_TIMESTAMP"
    fi
    
    if [ "$FORCE_RESTORE" = true ]; then
        if [ -f "$DATABASE_PATH" ]; then
            print_warning "Removing existing database (--force flag set)"
            rm -f "$DATABASE_PATH"
        fi
    else
        restore_cmd="$restore_cmd -if-db-not-exists -if-replica-exists"
    fi
    
    print_info "Executing restore command..."
    if eval "$restore_cmd"; then
        print_info "Restore command completed successfully"
        return 0
    else
        print_error "Restore command failed"
        return 1
    fi
}

verify_restored_db() {
    print_info "Verifying restored database..."
    
    if [ ! -f "$DATABASE_PATH" ]; then
        print_error "Database file does not exist after restore"
        return 1
    fi
    
    if [ ! -s "$DATABASE_PATH" ]; then
        print_error "Database file is empty after restore"
        return 1
    fi
    
    if [ -f "$PROJECT_ROOT/scripts/verify_database.py" ]; then
        if python3 "$PROJECT_ROOT/scripts/verify_database.py" 2>&1; then
            print_info "Database verification passed"
            return 0
        else
            print_error "Database verification failed"
            return 1
        fi
    else
        if command -v sqlite3 &> /dev/null; then
            if sqlite3 "$DATABASE_PATH" "PRAGMA integrity_check;" 2>/dev/null | grep -q "ok"; then
                print_info "Database integrity check passed"
                return 0
            else
                print_error "Database integrity check failed"
                return 1
            fi
        else
            print_warning "Cannot verify database (verification tools not available)"
            return 0
        fi
    fi
}

cleanup() {
    if [ -n "$LITESTREAM_CONFIG" ] && [ -f "$LITESTREAM_CONFIG" ]; then
        rm -f "$LITESTREAM_CONFIG"
    fi
}

trap cleanup EXIT

main() {
    echo "=========================================="
    echo "Emergency Database Restore"
    echo "=========================================="
    echo ""
    
    print_info "Verifying environment..."
    verify_environment
    
    check_litestream
    
    if [[ "$DATABASE_PATH" != /* ]]; then
        if [ -d "/app" ]; then
            DATABASE_PATH="/app/$DATABASE_PATH"
        else
            DATABASE_PATH="$PROJECT_ROOT/$DATABASE_PATH"
        fi
    fi
    
    print_info "Database path: $DATABASE_PATH"
    echo ""
    
    generate_config
    
    if ! verify_backup; then
        print_error "Cannot proceed without a valid backup"
        exit 1
    fi
    echo ""
    
    if [ -f "$DATABASE_PATH" ] && [ "$FORCE_RESTORE" = false ]; then
        print_warning "Database already exists at: $DATABASE_PATH"
        read -p "Do you want to backup the existing database before restore? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            backup_existing_db
        else
            BACKUP_BEFORE_RESTORE=false
        fi
        echo ""
    else
        backup_existing_db
    fi
    
    if ! restore_database; then
        print_error "Restore failed"
        exit 1
    fi
    echo ""
    
    if ! verify_restored_db; then
        print_error "Restored database verification failed"
        exit 1
    fi
    echo ""
    
    print_info "=========================================="
    print_info "Restore completed successfully!"
    print_info "=========================================="
    print_info "Database restored to: $DATABASE_PATH"
    if [ -n "$RESTORE_TIMESTAMP" ]; then
        print_info "Restored to timestamp: $RESTORE_TIMESTAMP"
    fi
    print_info ""
    print_info "Next steps:"
    print_info "1. Run database migrations if needed: python scripts/run_migrations.py"
    print_info "2. Verify application can connect to the database"
    print_info "3. Test critical functionality"
}

main

