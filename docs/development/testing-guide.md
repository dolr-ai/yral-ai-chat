# Testing Guide

## Testing Strategy

The application uses a multi-layered testing approach:

- **Unit Tests**: Test individual components in isolation
- **Integration Tests**: Test API endpoints and service interactions
- **End-to-End Tests**: Test complete user flows (future)

## Test Structure

```
tests/
├── unit/                    # Unit tests
│   ├── test_cache.py       # Cache functionality
│   ├── test_models.py      # Pydantic models
│   └── test_services.py    # Service layer
├── integration/             # Integration tests
│   ├── test_chat_endpoints.py
│   ├── test_influencer_endpoints.py
│   └── test_media_endpoints.py
├── conftest.py             # Shared fixtures
└── README.md               # This file
```

## Running Tests

### All Tests
```bash
pytest
```

### Specific Test File
```bash
pytest tests/unit/test_cache.py
```

### Specific Test Function
```bash
pytest tests/unit/test_cache.py::TestLRUCache::test_basic_set_get
```

### With Coverage
```bash
pytest --cov=src --cov-report=html
# Open htmlcov/index.html in browser
```

### Watch Mode
```bash
pytest-watch
```

### Verbose Output
```bash
pytest -vv
```

### Only Failed Tests
```bash
pytest --lf  # Last failed
pytest --ff  # Failed first, then others
```

## Writing Tests

### Unit Tests

**Example: Testing a service**

```python
import pytest
from src.services.my_service import MyService

class TestMyService:
    """Unit tests for MyService"""
    
    def test_process_data(self):
        """Test data processing"""
        service = MyService()
        result = service.process("input")
        assert result == "expected"
    
    def test_process_invalid_data(self):
        """Test error handling"""
        service = MyService()
        with pytest.raises(ValueError):
            service.process(None)
```

**Example: Testing cache**

```python
from src.core.cache import LRUCache

def test_cache_eviction():
    """Test LRU eviction when max size reached"""
    cache = LRUCache(max_size=2, default_ttl=60)
    
    cache.set("key1", "value1")
    cache.set("key2", "value2")
    cache.set("key3", "value3")  # Should evict key1
    
    assert cache.get("key1") is None  # Evicted
    assert cache.get("key2") == "value2"
    assert cache.get("key3") == "value3"
```

### Integration Tests

**Example: Testing API endpoint**

```python
import pytest
from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)

def test_create_conversation():
    """Test creating a conversation"""
    # Prepare auth token
    headers = {"Authorization": "Bearer test-token"}
    
    # Make request
    response = client.post(
        "/api/v1/chat/conversations",
        json={"influencer_id": "test-id"},
        headers=headers
    )
    
    # Assert response
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["influencer"]["id"] == "test-id"
```

**Example: Testing with database**

```python
import pytest
from src.db.repositories.conversation_repository import ConversationRepository

@pytest.mark.asyncio
async def test_create_conversation(test_db):
    """Test creating conversation in database"""
    repo = ConversationRepository()
    
    conversation = await repo.create(
        user_id="user123",
        influencer_id="inf456"
    )
    
    assert conversation.id is not None
    assert conversation.user_id == "user123"
    
    # Cleanup
    await repo.delete(conversation.id)
```

## Fixtures

### Shared Fixtures (`conftest.py`)

```python
import pytest
from fastapi.testclient import TestClient
from src.main import app
from src.db.base import db

@pytest.fixture
def client():
    """FastAPI test client"""
    return TestClient(app)

@pytest.fixture
async def test_db():
    """Test database connection"""
    await db.connect()
    yield db
    await db.disconnect()

@pytest.fixture
def mock_jwt_token():
    """Mock JWT token for testing"""
    return "Bearer test-token-123"

@pytest.fixture
def test_user():
    """Test user data"""
    return {
        "user_id": "test-user-123",
        "username": "testuser"
    }
```

### Using Fixtures

```python
def test_with_client(client):
    """Test using client fixture"""
    response = client.get("/health")
    assert response.status_code == 200

def test_with_multiple_fixtures(client, mock_jwt_token):
    """Test using multiple fixtures"""
    headers = {"Authorization": mock_jwt_token}
    response = client.get("/api/v1/chat/conversations", headers=headers)
    assert response.status_code == 200
```

## Mocking

### Mocking External Services

```python
from unittest.mock import Mock, patch, AsyncMock

@patch("src.services.gemini_client.GeminiClient.generate")
async def test_send_message_with_mock(mock_generate):
    """Test message sending with mocked AI service"""
    # Setup mock
    mock_generate.return_value = "AI response"
    
    # Test code
    service = ChatService()
    result = await service.send_message(
        conversation_id="conv123",
        content="Hello"
    )
    
    # Verify
    assert result.content == "AI response"
    mock_generate.assert_called_once()
```

### Mocking Async Functions

```python
@pytest.mark.asyncio
@patch("src.services.storage_service.StorageService.upload")
async def test_upload_with_mock(mock_upload):
    """Test file upload with mocked storage"""
    # Setup async mock
    mock_upload.return_value = "https://example.com/file.jpg"
    
    # Test
    service = StorageService()
    url = await service.upload(b"file content", "test.jpg")
    
    assert url == "https://example.com/file.jpg"
```

## Testing Best Practices

### 1. Test Organization

```python
class TestMyFeature:
    """Group related tests in classes"""
    
    def test_happy_path(self):
        """Test normal operation"""
        pass
    
    def test_error_case(self):
        """Test error handling"""
        pass
    
    def test_edge_case(self):
        """Test edge cases"""
        pass
```

### 2. Descriptive Names

```python
# Good
def test_cache_evicts_oldest_item_when_full():
    pass

# Bad
def test_cache():
    pass
```

### 3. AAA Pattern

```python
def test_feature():
    # Arrange: Setup test data
    cache = LRUCache(max_size=10)
    
    # Act: Perform action
    cache.set("key", "value")
    
    # Assert: Verify result
    assert cache.get("key") == "value"
```

### 4. One Assertion Per Test

```python
# Good
def test_cache_get_returns_value():
    cache = LRUCache()
    cache.set("key", "value")
    assert cache.get("key") == "value"

def test_cache_get_returns_none_for_missing_key():
    cache = LRUCache()
    assert cache.get("nonexistent") is None

# Avoid
def test_cache_operations():
    cache = LRUCache()
    cache.set("key", "value")
    assert cache.get("key") == "value"
    assert cache.get("other") is None  # Multiple concerns
```

### 5. Test Isolation

```python
# Good: Each test is independent
def test_feature_a():
    service = MyService()  # Fresh instance
    result = service.do_something()
    assert result == expected

def test_feature_b():
    service = MyService()  # Fresh instance
    result = service.do_other()
    assert result == expected
```

### 6. Mock External Dependencies

```python
@patch("src.services.gemini_client.GeminiClient")
def test_without_real_api(mock_client):
    """Don't make real API calls in tests"""
    mock_client.generate.return_value = "mocked response"
    # Test code
```

## Testing Async Code

### Async Test Functions

```python
import pytest

@pytest.mark.asyncio
async def test_async_function():
    """Test async function"""
    result = await my_async_function()
    assert result == expected
```

### Async Fixtures

```python
@pytest.fixture
async def async_resource():
    """Async fixture"""
    resource = await setup_resource()
    yield resource
    await cleanup_resource(resource)
```

## Coverage

### Generate Coverage Report

```bash
pytest --cov=src --cov-report=html --cov-report=term
```

### Coverage Configuration

`.coveragerc`:
```ini
[run]
source = src
omit = 
    */tests/*
    */venv/*
    */__pycache__/*

[report]
precision = 2
show_missing = True
skip_covered = False
```

### Coverage Goals

- **Overall**: >80%
- **Critical paths**: 100%
- **New code**: >90%

## Performance Testing

### Basic Performance Test

```python
import time

def test_cache_performance():
    """Test cache performance"""
    cache = LRUCache(max_size=1000)
    
    # Measure set performance
    start = time.time()
    for i in range(1000):
        cache.set(f"key{i}", f"value{i}")
    set_duration = time.time() - start
    
    # Measure get performance
    start = time.time()
    for i in range(1000):
        cache.get(f"key{i}")
    get_duration = time.time() - start
    
    # Assert reasonable performance
    assert set_duration < 1.0  # Less than 1 second
    assert get_duration < 0.5  # Less than 0.5 seconds
```

## Test Data

### Using Factories

```python
from datetime import datetime
from uuid import uuid4

class ConversationFactory:
    """Factory for creating test conversations"""
    
    @staticmethod
    def create(**kwargs):
        defaults = {
            "id": str(uuid4()),
            "user_id": "test-user",
            "influencer_id": "test-influencer",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        defaults.update(kwargs)
        return Conversation(**defaults)

# Usage
def test_with_factory():
    conversation = ConversationFactory.create(user_id="custom-user")
    assert conversation.user_id == "custom-user"
```

## Continuous Integration

### GitHub Actions

`.github/workflows/test.yml`:
```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt
      
      - name: Run tests
        run: pytest --cov=src --cov-report=xml
      
      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

## Debugging Tests

### Run with Debugger

```bash
pytest --pdb  # Drop into debugger on failure
pytest --pdbcls=IPython.terminal.debugger:Pdb  # Use IPython debugger
```

### Print Debug Info

```python
def test_debug():
    result = function_under_test()
    print(f"Debug: result = {result}")  # Will show in pytest output with -s
    assert result == expected
```

### Verbose Output

```bash
pytest -vv -s  # Very verbose, show print statements
```

## Common Testing Patterns

### Testing Exceptions

```python
def test_raises_exception():
    with pytest.raises(ValueError, match="Invalid input"):
        function_that_raises("bad input")
```

### Parametrized Tests

```python
@pytest.mark.parametrize("input,expected", [
    ("hello", "HELLO"),
    ("world", "WORLD"),
    ("test", "TEST"),
])
def test_uppercase(input, expected):
    assert input.upper() == expected
```

### Testing HTTP Responses

```python
def test_api_response(client):
    response = client.get("/api/v1/influencers")
    
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    
    data = response.json()
    assert "influencers" in data
    assert len(data["influencers"]) > 0
```

## Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [unittest.mock](https://docs.python.org/3/library/unittest.mock.html)
