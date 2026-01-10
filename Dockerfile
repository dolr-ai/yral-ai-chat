# Multi-stage Dockerfile for Yral AI Chat API with Litestream

# Stage 1: Build dependencies
FROM python:3.12-slim as builder

WORKDIR /build

# Install system dependencies for building Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt uvicorn[standard] uvloop httptools websockets

# Stage 2: Runtime image
FROM python:3.12-slim

WORKDIR /app

# Install runtime system dependencies + wget for Litestream
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    libsqlite3-0 \
    wget \
    ca-certificates \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Install Litestream
ARG LITESTREAM_VERSION=v0.3.13
RUN wget -qO- https://github.com/benbjohnson/litestream/releases/download/${LITESTREAM_VERSION}/litestream-${LITESTREAM_VERSION}-linux-amd64.tar.gz | \
    tar xvz -C /usr/local/bin

# Copy Python dependencies from builder
COPY --from=builder /root/.local /root/.local

# Make sure scripts in .local are usable
ENV PATH=/root/.local/bin:$PATH

# Copy application code
COPY src/ ./src/
COPY migrations/ ./migrations/
COPY scripts/run_migrations.py ./scripts/run_migrations.py
COPY scripts/verify_database.py ./scripts/verify_database.py

# Copy Litestream config and entrypoint
COPY config/litestream.yml /etc/litestream.yml
COPY scripts/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Create necessary directories
RUN mkdir -p /app/data /app/uploads /app/logs

# Set working directory
WORKDIR /app

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Use entrypoint script to start both Litestream and the app
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
