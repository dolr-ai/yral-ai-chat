# Dockerfile for bare metal deployment
FROM ubuntu:noble

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    wget \
    sqlite3 \
    gettext-base \
    && rm -rf /var/lib/apt/lists/*

# Install Litestream for SQLite replication
RUN wget -q https://github.com/benbjohnson/litestream/releases/download/v0.3.13/litestream-v0.3.13-linux-amd64.tar.gz -O /tmp/litestream.tar.gz \
    && tar -xzf /tmp/litestream.tar.gz -C /usr/local/bin/ \
    && rm /tmp/litestream.tar.gz \
    && chmod +x /usr/local/bin/litestream

# Create data directory for SQLite
RUN mkdir -p /app/data /app/migrations/sqlite

# Copy the binary
COPY ./target/x86_64-unknown-linux-gnu/release/yral-ai-chat .

# Copy migrations
COPY ./migrations/sqlite/ /app/migrations/sqlite/

# Copy Litestream config
COPY ./deploy-baremetal/litestream.yml /etc/litestream.yml

# Copy entrypoint script
COPY ./deploy-baremetal/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Expose HTTP port
EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
