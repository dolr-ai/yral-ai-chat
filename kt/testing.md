# 6. Testing & Monitoring

## Testing Strategy

The project uses `pytest` for all testing. Tests are designed to run in two modes:

1. **Local (Mocked)**: Uses `FastAPI.TestClient` and in-memory SQLite (`:memory:`). No external services required.
2. **Remote (Integration)**: Tests against a running staging/production server via HTTP requests.

## Running Tests

### Unit/Local Tests

Run these during development for fast feedback.

```bash
# Run all tests
pytest

# Run a specific test file
pytest tests/api/test_chat_params.py

# Run with coverage report
pytest --cov=src --cov-report=term-missing
```

## Linting & Code Quality

We use several tools to maintain a high bar for code quality:

- **Ruff**: Extremely fast Python linter and code formatter (replaces Black, Isort, Flake8).
- **Black**: (Optional/Legacy check) for formatting ensuring consistency.
- **Mypy**: Static type checking to catch type-related bugs early.

Run all checks via:

```bash
ruff check src tests
ruff format src tests
mypy src
```

### Integration/Remote Tests

Run these to verify a deployed environment.

```bash
TEST_API_URL=https://staging.chat.yral.com pytest
```

## Key Test Files

- `tests/conftest.py`: Shared fixtures.
  - **`client`**: Adapts between `TestClient` (local) and `actions` (remote).
  - **`auth_headers`**: Generates a dummy JWT for testing (backend validates signature only if configured, but for tests we often mock or use a known secret).
  - **`disable_sentry_during_tests`**: Prevents noise in Sentry.
- `tests/api/`: API endpoint tests.

## Monitoring

- **Sentry**: Error tracking. Configured in `src/main.py`.
- **Logging**: Uses `loguru` for structured JSON logging.
