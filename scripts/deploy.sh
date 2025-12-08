#!/bin/bash
# Deployment script for Yral AI Chat
# Usage: ./scripts/deploy.sh [--skip-build] [--health-check]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_DIR"

SKIP_BUILD=false
HEALTH_CHECK=true

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-build)
            SKIP_BUILD=true
            shift
            ;;
        --no-health-check)
            HEALTH_CHECK=false
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--skip-build] [--no-health-check]"
            exit 1
            ;;
    esac
done

echo "=========================================="
echo "🚀 Deploying Yral AI Chat"
echo "=========================================="
echo ""

# Check if required environment variables are set
REQUIRED_VARS=("JWT_SECRET_KEY" "GEMINI_API_KEY")
MISSING_VARS=()

for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var}" ]; then
        MISSING_VARS+=("$var")
    fi
done

if [ ${#MISSING_VARS[@]} -ne 0 ]; then
    echo "❌ Error: Missing required environment variables:"
    for var in "${MISSING_VARS[@]}"; do
        echo "   - $var"
    done
    echo ""
    echo "Please set these variables before running deployment."
    exit 1
fi

# Build Docker image if not skipping
if [ "$SKIP_BUILD" = false ]; then
    echo "📦 Building Docker image..."
    docker compose build
    echo "✅ Build complete"
    echo ""
fi

# Stop existing containers
echo "🛑 Stopping existing containers..."
docker compose down
echo "✅ Containers stopped"
echo ""

# Start containers with environment variables
echo "🚀 Starting containers..."
docker compose up -d
echo "✅ Containers started"
echo ""

# Wait for container to be ready
echo "⏳ Waiting for service to be ready..."
sleep 5

# Run database migrations if needed
echo "🗄️  Checking database migrations..."
if [ -f "migrations/sqlite/001_init_schema.sql" ]; then
    # Check if database exists
    if [ ! -f "data/yral_chat.db" ]; then
        echo "   Creating database and running migrations..."
        docker compose exec -T yral-ai-chat python scripts/run_migrations.py || echo "   ⚠️  Migration may have already been applied"
    else
        echo "   ✅ Database already exists"
        echo "   ℹ️  To run migrations on existing database, use: docker compose exec yral-ai-chat python /app/scripts/run_migrations.py"
    fi
else
    echo "   ⚠️  Migration files not found, skipping"
fi
echo ""

# Health check
if [ "$HEALTH_CHECK" = true ]; then
    echo "🏥 Running health check..."
    max_attempts=10
    attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if curl -f -s http://localhost:8000/health > /dev/null 2>&1; then
            echo "   ✅ Health check passed (attempt $attempt/$max_attempts)"
            break
        else
            if [ $attempt -eq $max_attempts ]; then
                echo "   ❌ Health check failed after $max_attempts attempts"
                echo "   Check logs with: docker compose logs yral-ai-chat"
                exit 1
            else
                echo "   ⏳ Waiting for service... (attempt $attempt/$max_attempts)"
                sleep 3
                attempt=$((attempt + 1))
            fi
        fi
    done
    echo ""
fi

# Show container status
echo "📊 Container status:"
docker compose ps
echo ""

# Show logs
echo "📋 Recent logs:"
docker compose logs --tail=20 yral-ai-chat
echo ""

echo "=========================================="
echo "✅ Deployment complete!"
echo "=========================================="
echo ""
echo "Service is running at: http://localhost:8000"
echo "API docs: http://localhost:8000/docs"
echo "Health check: http://localhost:8000/health"
echo ""
echo "Useful commands:"
echo "  View logs:    docker compose logs -f yral-ai-chat"
echo "  Stop service: docker compose down"
echo "  Restart:      docker compose restart yral-ai-chat"
echo ""

