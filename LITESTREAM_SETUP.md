# Litestream Setup Guide

Litestream provides real-time replication of your SQLite database to S3-compatible storage (Hetzner Object Storage).

## ⚠️ Known Issue with Hetzner S3

**Generation Tracking Error**: Litestream may show repeated "monitor error: cannot determine replica position: no snapshot available" messages. This is due to Hetzner's S3-compatible storage not fully supporting all S3 operations that Litestream expects.

**Impact**:
- ✅ **Snapshots ARE being created successfully** (your data is backed up)
- ✅ **WAL files are being synced** (incremental changes are captured)
- ⚠️ **Generation metadata tracking is broken** (may affect point-in-time recovery)
- ⚠️ **Monitor errors are cosmetic** (backups still work)

**Recommendation**: Despite the errors, your database backups are functional. Monitor the S3 bucket to verify snapshots are appearing regularly.

## Prerequisites

- SQLite database with WAL mode enabled
- S3-compatible storage credentials (Hetzner Object Storage)
- Litestream binary installed

## Installation

### macOS (Local Development)

```bash
# Install via Homebrew
brew install litestream

# Verify installation
litestream version
```

### Linux (Production Server)

```bash
# Download and install Litestream
wget https://github.com/benbjohnson/litestream/releases/download/v0.3.13/litestream-v0.3.13-linux-amd64.deb
sudo dpkg -i litestream-v0.3.13-linux-amd64.deb
rm litestream-v0.3.13-linux-amd64.deb

# Verify installation
litestream version
```

## Configuration

### 1. Enable WAL Mode on Database

Litestream requires SQLite to be in WAL (Write-Ahead Logging) mode:

```bash
sqlite3 data/yral_chat.db "PRAGMA journal_mode=WAL;"
```

### 2. Configuration Files

Two configuration files are provided:

- **`config/litestream.yml`** - Production server (absolute paths)
- **`config/litestream-local.yml`** - Local development (relative paths)

**Key differences:**
- Production: Syncs every 10s, snapshots hourly, 7-day retention
- Development: Syncs every 30s, snapshots every 6h, 3-day retention
- Production path: `/root/yral-ai-chat/data/yral_chat.db`
- Development path: `./data/yral_chat.db`

### 3. S3 Bucket Structure

Files are stored in S3 as:
```
postgres-1-backup/
├── yral-ai-chat/db/          # Production backups
│   ├── generations/
│   ├── snapshots/
│   └── wal/
└── yral-ai-chat-dev/db/      # Development backups
    ├── generations/
    ├── snapshots/
    └── wal/
```

## Running Litestream

### Local Development (macOS)

```bash
# Start Litestream in foreground (for testing)
litestream replicate -config config/litestream-local.yml

# Or run in background
litestream replicate -config config/litestream-local.yml &

# Check status
litestream databases -config config/litestream-local.yml
```

### Production Server (Linux)

#### Automated Installation

Use the provided installation script for quick setup:

```bash
# On your production server, run as root:
cd /root/yral-ai-chat
sudo ./scripts/install_litestream_prod.sh
```

This script will:
1. Download and install Litestream v0.3.13
2. Enable WAL mode on the database
3. Install and start the systemd service
4. Verify the setup

#### Manual Systemd Service Setup

If you prefer manual installation:

```bash
# Copy service file
sudo cp config/litestream.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable service (start on boot)
sudo systemctl enable litestream

# Start service
sudo systemctl start litestream

# Check status
sudo systemctl status litestream

# View logs
journalctl -u litestream -f
```

#### Manual Run (for testing)

```bash
# Run in foreground
litestream replicate -config config/litestream.yml

# Run in background
litestream replicate -config config/litestream.yml &
```

## Verification

### Check Replication Status

```bash
# List databases being replicated
litestream databases -config config/litestream.yml

# Show detailed replication info
litestream snapshots -config config/litestream.yml /root/yral-ai-chat/data/yral_chat.db
```

### Monitor Logs

**Local development:**
```bash
# Litestream outputs to stdout when run manually
litestream replicate -config config/litestream-local.yml
```

**Production:**
```bash
# Systemd logs
journalctl -u litestream -f

# Log files (if configured)
tail -f /root/yral-ai-chat/logs/litestream.log
tail -f /root/yral-ai-chat/logs/litestream-error.log
```

### Check S3 Bucket

Verify files are being uploaded to S3:

```bash
# Using AWS CLI (with S3-compatible endpoint)
aws s3 ls s3://postgres-1-backup/yral-ai-chat/db/ \
  --endpoint-url=https://postgres-1-backup.hel1.your-objectstorage.com

# Or check via Hetzner Cloud Console
```

## Restoring from Backup

### Full Restore

```bash
# Stop the application first
sudo systemctl stop yral-ai-chat

# Restore from latest backup
litestream restore -config config/litestream.yml \
  -o data/yral_chat.db

# Restart application
sudo systemctl start yral-ai-chat
```

### Restore to Specific Point in Time

```bash
# Restore to specific timestamp
litestream restore -config config/litestream.yml \
  -timestamp 2024-12-15T10:00:00Z \
  -o data/yral_chat.db

# Restore to specific generation
litestream restore -config config/litestream.yml \
  -generation abc123 \
  -o data/yral_chat.db
```

## Troubleshooting

### Check WAL Mode

```bash
sqlite3 data/yral_chat.db "PRAGMA journal_mode;"
# Should output: wal
```

### Enable WAL Mode

```bash
sqlite3 data/yral_chat.db "PRAGMA journal_mode=WAL;"
```

### Permission Issues

```bash
# Ensure correct ownership
sudo chown -R root:root /root/yral-ai-chat/data
sudo chmod 644 /root/yral-ai-chat/data/yral_chat.db*
```

### S3 Connection Issues

1. Verify credentials in `config/litestream.yml`
2. Check S3 endpoint URL is correct
3. Ensure bucket exists and is accessible
4. Test with AWS CLI:

```bash
aws s3 ls s3://postgres-1-backup/ \
  --endpoint-url=https://postgres-1-backup.hel1.your-objectstorage.com \
  --profile hetzner
```

### Service Won't Start

```bash
# Check service status
sudo systemctl status litestream

# View detailed logs
journalctl -u litestream -n 50 --no-pager

# Test configuration manually
litestream replicate -config config/litestream.yml
```

## Configuration Details

### Replication Settings

- **sync-interval**: How often to sync WAL changes to S3
- **snapshot-interval**: How often to create full database snapshots
- **retention**: How long to keep WAL files
- **retention-check-interval**: How often to check and clean old files

### Production Values (Recommended)

```yaml
sync-interval: 10s        # Balance between performance and data loss
snapshot-interval: 1h     # Regular snapshots for point-in-time recovery
retention: 168h           # 7 days of history
```

### Development Values

```yaml
sync-interval: 30s        # Less frequent to reduce S3 costs
snapshot-interval: 6h     # Less frequent snapshots
retention: 72h            # 3 days of history
```

## Security Notes

1. **Credentials**: The `litestream.yml` file contains S3 credentials. Keep it secure:
   ```bash
   chmod 600 config/litestream.yml
   ```

2. **Backup Encryption**: Litestream supports encryption at rest. To enable:
   ```yaml
   replicas:
     - type: s3
       # ... other config ...
       encryption: aes256
   ```

3. **Access Control**: Ensure S3 bucket has appropriate access policies

## Monitoring

Set up alerts for:
- Litestream service status
- Replication lag
- Failed uploads
- Disk space for WAL files

Example check script:
```bash
#!/bin/bash
if ! systemctl is-active --quiet litestream; then
    echo "Litestream is not running!"
    # Send alert
fi
```

## Resources

- [Litestream Documentation](https://litestream.io/)
- [Litestream GitHub](https://github.com/benbjohnson/litestream)
- [S3-Compatible Storage Guide](https://litestream.io/guides/s3/)
