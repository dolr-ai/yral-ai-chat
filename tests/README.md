# API Tests

Simple, clean unit tests that ping the API and assert responses.

## Running the Tests

Just run pytest:

```bash
pytest tests/ -v
```

That's it! FastAPI TestClient handles everything automatically - no need to manually start a server.

## Prerequisites

Make sure your `src/config.py` includes these fields (if using local storage):

```python
media_upload_dir: str = Field(default="uploads", alias="MEDIA_UPLOAD_DIR")
media_base_url: str = Field(default="http://localhost:8000/media", alias="MEDIA_BASE_URL")
```

And your `.env` file has the corresponding values.

## Test Coverage

- **test_health_endpoints.py** (5 tests) - `/`, `/health`, `/status`
- **test_influencer_endpoints.py** (9 tests) - List and get influencers
- **test_chat_endpoints.py** (19 tests) - Conversations and messages
- **test_media_endpoints.py** (6 tests) - Media upload validation

**Total: 39 tests**

## Quick Examples

Run all tests:
```bash
pytest tests/ -v
```

Run specific test file:
```bash
pytest tests/test_health_endpoints.py -v
```

Run single test:
```bash
pytest tests/test_health_endpoints.py::test_root_endpoint -v
```
