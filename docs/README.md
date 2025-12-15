# Documentation

Welcome to the Yral AI Chat API documentation.

## Table of Contents

### API Documentation
- **[API Specification](api/)** - OpenAPI/Swagger documentation
- **[API Contract](../API_CONTRACT.md)** - Detailed API contracts and examples

### Architecture
- **[System Architecture](architecture/system-design.md)** - High-level system design
- **[Database Schema](architecture/database.md)** - Database structure and relationships

### Development
- **[Getting Started](../README.md)** - Setup and installation
- **[Development Guide](development/development-guide.md)** - Development workflow
- **[Testing Guide](development/testing-guide.md)** - Testing strategies

### Deployment
- **[Deployment Guide](../LITESTREAM_PROD_DEPLOY.md)** - Production deployment
- **[Litestream Setup](../LITESTREAM_SETUP.md)** - Database replication

### Implementation
- **[Implementation Summary](../IMPLEMENTATION_SUMMARY.md)** - Recent improvements and features

## Quick Links

- **Interactive API Docs**: http://localhost:8000/docs (when server is running)
- **Health Check**: http://localhost:8000/health
- **Metrics**: http://localhost:8000/metrics

## For Developers

### Local Development
```bash
# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Run migrations
python scripts/run_migrations.py

# Start server
uvicorn src.main:app --reload

# Run tests
pytest

# Export OpenAPI spec
python scripts/export_openapi_spec.py
```

### Code Quality
```bash
# Format code
black src/ tests/

# Lint
ruff check src/ tests/

# Type check
mypy src/
```

## Support

For questions or issues:
1. Check the relevant documentation section
2. Review the [API Contract](../API_CONTRACT.md)
3. Check the interactive docs at `/docs` when the server is running
4. Review implementation notes in [IMPLEMENTATION_SUMMARY.md](../IMPLEMENTATION_SUMMARY.md)
