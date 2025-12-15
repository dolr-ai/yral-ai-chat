# Scripts Directory

This directory contains various deployment and setup scripts for the Yral AI Chat API.

## Development Scripts

### `run_migrations.py`
**Purpose**: Run SQLite database migrations  
**Usage**: `python scripts/run_migrations.py`  
**When to use**: 
- During initial setup
- After pulling schema changes
- When resetting the database

### `start_litestream_local.sh`
**Purpose**: Start Litestream replication for local development (macOS)  
**Usage**: `./scripts/start_litestream_local.sh`  
**When to use**:
- When testing Litestream locally
- For development with S3 backup enabled
**Prerequisites**: Litestream binary in `./bin/` directory

## Production Setup Scripts (One-Time Use)

### `setup_sqlite_litestream.sh`
**Purpose**: ONE-TIME setup of SQLite + Litestream on a fresh production server  
**Usage**: `sudo ./scripts/setup_sqlite_litestream.sh`  
**When to use**: Only once when setting up a new production server  
**What it does**:
- Installs Litestream
- Creates database with schema
- Configures systemd services
- Enables WAL mode

### `install_litestream_prod.sh`
**Purpose**: ONE-TIME installation of Litestream binary on production  
**Usage**: `sudo ./scripts/install_litestream_prod.sh`  
**When to use**: Only once on new servers  
**What it does**:
- Downloads and installs Litestream binary
- Sets up systemd service
- Enables WAL mode on database

### `setup_systemd.sh`
**Purpose**: ONE-TIME setup of the application as a systemd service  
**Usage**: `sudo ./scripts/setup_systemd.sh`  
**When to use**: Only once on new servers (if not using Docker)  
**What it does**:
- Installs systemd service file
- Enables auto-start on boot
- Starts the service

### `setup_nginx.sh`
**Purpose**: ONE-TIME setup of Nginx reverse proxy with SSL  
**Usage**: `sudo ./scripts/setup_nginx.sh`  
**When to use**: Only once on new servers  
**What it does**:
- Installs Nginx and Certbot
- Configures reverse proxy
- Sets up SSL certificate with Let's Encrypt
- Configures firewall rules

## Deployment Scripts (Recurring Use)

### `deploy.sh`
**Purpose**: Deploy application updates using Docker  
**Usage**: `./scripts/deploy.sh [--skip-build] [--no-health-check]`  
**When to use**: 
- After code changes
- For regular deployments
- Can be used in CI/CD pipelines
**What it does**:
- Builds Docker image (optional)
- Stops old containers
- Starts new containers
- Runs health checks
- Handles database migrations

## Script Usage Recommendations

### For New Production Server Setup:
```bash
# 1. Clone the repository
git clone <repo-url> /root/yral-ai-chat
cd /root/yral-ai-chat

# 2. Set up environment variables
cp env.example .env
nano .env  # Fill in all credentials

# 3. Run one-time setup scripts (choose one approach)

# Option A: Using Docker (recommended)
./scripts/deploy.sh

# Option B: Using systemd services
sudo ./scripts/setup_sqlite_litestream.sh
sudo ./scripts/setup_systemd.sh
sudo ./scripts/setup_nginx.sh
```

### For Regular Deployments:
```bash
# Pull latest code
git pull origin main

# Deploy with Docker
./scripts/deploy.sh

# Or restart systemd service
sudo systemctl restart yral-ai-chat
```

### For Local Development:
```bash
# 1. Run migrations
python scripts/run_migrations.py

# 2. (Optional) Start Litestream for backups
./scripts/start_litestream_local.sh

# 3. Run the app
uvicorn src.main:app --reload
```

## Notes

- **One-time scripts** should only be run once during initial server setup
- **Deployment scripts** can be run multiple times for updates
- All production scripts require root/sudo access
- Environment variables must be configured before running any deployment
- See `LITESTREAM_SETUP.md` for detailed Litestream configuration
