# Test Suite

Comprehensive test suite for the Yral AI Chat API.

## Structure

```
tests/
├── unit/                      # Unit tests
│   ├── test_cache.py         # Cache functionality (16 tests)
│   ├── test_models.py        # Pydantic models (9 tests)
│   └── test_services.py      # Service layer (placeholders)
├── integration/               # Integration tests  
│   ├── test_chat_endpoints.py         # Chat API (19 tests)
│   ├── test_health_endpoints.py       # Health checks (5 tests)
│   ├── test_influencer_endpoints.py   # Influencer API (9 tests)
│   └── test_media_endpoints.py        # Media upload (6 tests)
├── conftest.py               # Shared fixtures
└── README.md                 # This file
```

## Running Tests

### All Tests
```bash
pytest
```

### Unit Tests Only
```bash
pytest tests/unit/
```

### Integration Tests Only
```bash
pytest tests/integration/
```

### Specific Test File
```bash
pytest tests/unit/test_cache.py -v
```

### With Coverage
```bash
pytest --cov=src --cov-report=html
# View coverage: open htmlcov/index.html
```

### Verbose Output
```bash
pytest -vv
```

### Watch Mode (auto-rerun on changes)
```bash
pytest-watch
```

## Test Categories

### Unit Tests (`tests/unit/`)

Test individual components in isolation:
- **Cache**: LRU eviction, TTL expiration, statistics
- **Models**: Pydantic validation, field constraints
- **Services**: Business logic (placeholder tests - expand as needed)

### Integration Tests (`tests/integration/`)

Test API endpoints with real or mocked dependencies:
- **Health**: Health checks, system status
- **Influencers**: List and retrieve influencers
- **Chat**: Conversations, messages, context management
- **Media**: File upload validation

## Prerequisites

Ensure environment is configured:

1. **Virtual environment activated**
   ```bash
   source venv/bin/activate
   ```

2. **Dependencies installed**
   ```bash
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   ```

3. **Environment variables set** (`.env` file)
   ```env
   DATABASE_PATH=data/test.db
   GEMINI_API_KEY=test-key
   AWS_ACCESS_KEY_ID=test-key
   AWS_SECRET_ACCESS_KEY=test-secret
   ```

## Writing Tests

### Example Unit Test

```python
def test_cache_eviction():
    """Test LRU eviction when max size reached"""
    cache = LRUCache(max_size=2)
    cache.set("key1", "value1")
    cache.set("key2", "value2")
    cache.set("key3", "value3")  # Evicts key1
    
    assert cache.get("key1") is None
    assert cache.get("key2") == "value2"
```

### Example Integration Test

```python
def test_list_influencers(client):
    """Test listing influencers"""
    response = client.get("/api/v1/influencers")
    
    assert response.status_code == 200
    data = response.json()
    assert "influencers" in data
    assert len(data["influencers"]) > 0
```

## Test Coverage

Current coverage:
- **Unit Tests**: ~25 tests
- **Integration Tests**: ~39 tests
- **Total**: ~64 tests

Coverage goal: >80% overall, 100% for critical paths

## Continuous Integration

Tests run automatically on:
- Push to any branch
- Pull request creation
- Pre-merge checks

## Documentation

For detailed testing guidelines and best practices:
- [Testing Guide](../docs/development/testing-guide.md)
- [Development Guide](../docs/development/development-guide.md)

## Quick Reference

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test
pytest tests/unit/test_cache.py::TestLRUCache::test_basic_set_get

# Run tests matching pattern
pytest -k "cache"

# Show print statements
pytest -s

# Stop on first failure
pytest -x

# Re-run last failed
pytest --lf
```
