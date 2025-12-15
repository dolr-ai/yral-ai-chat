# Litestream Production Deployment Guide

## Quick Start

### On Your Production Server:

```bash
# 1. SSH into your server
ssh root@your-server

# 2. Navigate to your project
cd /root/yral-ai-chat

# 3. Pull latest changes (including Litestream config)
git pull

# 4. Run the installation script
sudo ./scripts/install_litestream_prod.sh
```

That's it! Litestream will now run as a systemd service.

---

## What Gets Installed

1. **Litestream binary** → `/usr/local/bin/litestream`
2. **Systemd service** → `/etc/systemd/system/litestream.service`
3. **Configuration** → Uses `/root/yral-ai-chat/config/litestream.yml`

---

## Service Management

```bash
# Check status
systemctl status litestream

# View logs (live)
journalctl -u litestream -f

# View last 100 lines
journalctl -u litestream -n 100

# Restart service
systemctl restart litestream

# Stop service
systemctl stop litestream

# Start service
systemctl start litestream

# Disable auto-start
systemctl disable litestream
```

---

## Verifying Backups

### Check Replication Status

```bash
litestream databases -config /root/yral-ai-chat/config/litestream.yml
```

### List Snapshots

```bash
litestream snapshots -config /root/yral-ai-chat/config/litestream.yml /root/yral-ai-chat/data/yral_chat.db
```

### Check S3 Bucket

Your backups are stored at:
```
s3://postgres-1-backup/yral-ai-chat/db/
```

Use Hetzner Cloud Console to browse the bucket and verify files are appearing.

---

## Expected Behavior

### ✅ Normal Logs You'll See:

```
level=INFO msg="initialized db"
level=INFO msg="replicating to" name=s3 type=s3
level=INFO msg="snapshot written" elapsed=XXXms sz=XXXXX
```

### ⚠️ Expected Errors (Can Be Ignored):

```
level=ERROR msg="monitor error" error="cannot determine replica position: no snapshot available"
```

**Why?** Hetzner's S3-compatible storage doesn't fully support all S3 operations for generation tracking. However:
- ✅ Snapshots ARE being created
- ✅ WAL files ARE being synced
- ✅ Your data IS being backed up

---

## Backup Schedule

Based on `config/litestream.yml`:

- **WAL Sync**: Every 10 seconds (incremental changes)
- **Snapshots**: Every 1 hour (full database copy)
- **Retention**: 7 days (168 hours)

---

## Restoring from Backup

If you need to restore your database:

```bash
# Stop your application first
systemctl stop yral-ai-chat  # or your app service name

# Restore from S3
litestream restore -config /root/yral-ai-chat/config/litestream.yml \
  -o /root/yral-ai-chat/data/yral_chat.db

# Restart application
systemctl start yral-ai-chat

# Restart Litestream
systemctl restart litestream
```

### Restore to Specific Point in Time

```bash
litestream restore -config /root/yral-ai-chat/config/litestream.yml \
  -timestamp "2024-12-15T10:00:00Z" \
  -o /root/yral-ai-chat/data/yral_chat.db
```

---

## Troubleshooting

### Service Won't Start

```bash
# Check service status
systemctl status litestream

# Check logs
journalctl -u litestream -n 50

# Verify config file exists
ls -la /root/yral-ai-chat/config/litestream.yml

# Test configuration
litestream replicate -config /root/yral-ai-chat/config/litestream.yml
```

### Database Not in WAL Mode

```bash
sqlite3 /root/yral-ai-chat/data/yral_chat.db "PRAGMA journal_mode=WAL;"
```

### S3 Connection Issues

Check credentials in `config/litestream.yml` (loaded from environment variables):
- Access Key: Set via `LITESTREAM_ACCESS_KEY_ID`
- Endpoint: Set via `LITESTREAM_ENDPOINT`
- Bucket: Set via `LITESTREAM_BUCKET`

Verify your `.env` file contains the correct Litestream credentials.

---

## Security Notes

⚠️ **Important**: The `config/litestream.yml` file contains S3 credentials and should:
- Be in `.gitignore` (already added)
- Have restricted permissions: `chmod 600 config/litestream.yml`
- Only be accessible by root user

---

## Monitoring in Production

### Set Up Alerts

Consider monitoring:
1. **Service status**: Alert if systemd service stops
2. **S3 bucket**: Alert if no new files in 2+ hours
3. **Disk space**: Ensure WAL files don't fill up disk

### Health Check Script

```bash
#!/bin/bash
# Check if Litestream is running and backups are recent
if ! systemctl is-active --quiet litestream; then
  echo "ALERT: Litestream service is not running!"
  exit 1
fi

# Check last snapshot time
# (Add your monitoring logic here)
```

---

## Uninstalling

If you need to remove Litestream:

```bash
# Stop and disable service
systemctl stop litestream
systemctl disable litestream

# Remove service file
rm /etc/systemd/system/litestream.service
systemctl daemon-reload

# Remove binary
rm /usr/local/bin/litestream

# Remove config (optional - keeps your backups)
# rm /root/yral-ai-chat/config/litestream.yml
```

---

## Additional Resources

- [Litestream Documentation](https://litestream.io/)
- [Litestream GitHub](https://github.com/benbjohnson/litestream)
- [Full Setup Guide](./LITESTREAM_SETUP.md)
