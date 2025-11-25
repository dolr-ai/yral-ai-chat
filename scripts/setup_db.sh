#!/bin/bash
# Database setup script for Yral AI Chat

set -e

echo "Setting up PostgreSQL database for Yral AI Chat..."

# Database credentials
DB_NAME="yral_chat"
DB_USER="yral_chat_user"
DB_PASSWORD="yral_password_2024"

# Check if PostgreSQL is installed
if ! command -v psql &> /dev/null; then
    echo "Error: PostgreSQL is not installed"
    echo "Install with: sudo apt-get install postgresql postgresql-contrib"
    exit 1
fi

# Check if PostgreSQL is running
if ! sudo systemctl is-active --quiet postgresql; then
    echo "Starting PostgreSQL service..."
    sudo systemctl start postgresql
fi

echo "Creating database and user..."

# Create user and database
sudo -u postgres psql <<EOF
-- Create user if not exists
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_user WHERE usename = '$DB_USER') THEN
        CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';
    END IF;
END
\$\$;

-- Drop database if exists (for fresh install)
DROP DATABASE IF EXISTS $DB_NAME;

-- Create database
CREATE DATABASE $DB_NAME OWNER $DB_USER;

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;

\c $DB_NAME

-- Grant schema privileges
GRANT ALL ON SCHEMA public TO $DB_USER;

-- Ensure user can create extensions
ALTER DATABASE $DB_NAME OWNER TO $DB_USER;

EOF

echo "✅ Database '$DB_NAME' created successfully"
echo "✅ User '$DB_USER' created with password '$DB_PASSWORD'"
echo ""
echo "Next steps:"
echo "1. Run migrations: psql -U $DB_USER -d $DB_NAME -f migrations/001_init_schema.sql"
echo "2. Seed data: psql -U $DB_USER -d $DB_NAME -f migrations/002_seed_influencers.sql"
echo ""
echo "Connection string:"
echo "postgresql://$DB_USER:$DB_PASSWORD@localhost:5432/$DB_NAME"

