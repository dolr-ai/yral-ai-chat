# Development Guide

## Getting Started

### Prerequisites

- Python 3.12+
- pip or uv
- Git
- SQLite3

### Initial Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd yral-ai-chat
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   ```

4. **Configure environment**
   ```bash
   cp env.example .env
   # Edit .env with your configuration
   ```

5. **Run migrations**
   ```bash
   python scripts/run_migrations.py
   ```

6. **Start development server**
   ```bash
   uvicorn src.main:app --reload --port 8000
   ```

## Project Structure

```
yral-ai-chat/
├── src/                    # Application source code
│   ├── api/               # API routes
│   │   └── v1/           # API version 1
│   ├── auth/             # Authentication
│   ├── core/             # Core utilities
│   ├── db/               # Database layer
│   ├── middleware/       # Middleware
│   ├── models/           # Pydantic models
│   ├── services/         # Business logic
│   ├── config.py         # Configuration
│   └── main.py           # Application entry
├── tests/                 # Test suite
│   ├── unit/             # Unit tests
│   └── integration/      # Integration tests
├── migrations/           # Database migrations
├── scripts/              # Utility scripts
├── docs/                 # Documentation
└── requirements.txt      # Dependencies
```

## Development Workflow

### 1. Feature Development

```bash
# Create feature branch
git checkout -b feature/your-feature-name

# Make changes
# ...

# Run tests
pytest

# Commit changes
git add .
git commit -m "Add feature: description"

# Push and create PR
git push origin feature/your-feature-name
```

### 2. Code Quality

**Format code:**
```bash
black src/ tests/
```

**Lint:**
```bash
ruff check src/ tests/
```

**Type check:**
```bash
mypy src/
```

**Run all checks:**
```bash
ruff check src/ tests/
```

### 3. Testing

**Run all tests:**
```bash
pytest
```

**Run specific test file:**
```bash
pytest tests/unit/test_cache.py
```

**Run with coverage:**
```bash
pytest --cov=src --cov-report=html
```

**Run integration tests:**
```bash
pytest tests/integration/
```

## API Development

### Adding a New Endpoint

1. **Define request/response models** in `src/models/`
   ```python
   class MyRequest(BaseModel):
       field: str = Field(..., description="Description")
   ```

2. **Create endpoint** in `src/api/v1/`
   ```python
   @router.post(
       "/my-endpoint",
       response_model=MyResponse,
       operation_id="myOperation",
       summary="Brief description"
   )
   async def my_endpoint(request: MyRequest):
       # Implementation
       pass
   ```

3. **Add business logic** in `src/services/`
   ```python
   class MyService:
       async def do_something(self, data):
           # Logic here
           pass
   ```

4. **Write tests** in `tests/`
   ```python
   def test_my_endpoint():
       response = client.post("/api/v1/my-endpoint", json={...})
       assert response.status_code == 200
   ```

5. **Update OpenAPI spec**
   ```bash
   python scripts/export_openapi_spec.py
   ```

### Service Layer Development

Follow the repository pattern:

```python
# Repository (Data Access)
class MyRepository:
    async def get_by_id(self, id: str):
        return await db.fetchone("SELECT * FROM table WHERE id = ?", id)

# Service (Business Logic)
class MyService:
    def __init__(self, repo: MyRepository):
        self.repo = repo
    
    async def process(self, id: str):
        data = await self.repo.get_by_id(id)
        # Business logic
        return result

# Dependency Injection
def get_my_service() -> MyService:
    return MyService(MyRepository())
```

## Database Development

### Creating Migrations

1. Create SQL file: `migrations/sqlite/NNN_description.sql`
2. Write migration:
   ```sql
   -- Create new table
   CREATE TABLE my_table (
       id TEXT PRIMARY KEY,
       name TEXT NOT NULL,
       created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
   );
   
   -- Create index
   CREATE INDEX idx_my_table_name ON my_table(name);
   ```
3. Run migrations:
   ```bash
   python scripts/run_migrations.py
   ```

### Working with Database

**Using the connection pool:**
```python
from src.db.base import db

# Execute query
result = await db.fetchone("SELECT * FROM table WHERE id = ?", id)

# Execute many
results = await db.fetchall("SELECT * FROM table WHERE active = ?", True)

# Execute with transaction
async with db.transaction():
    await db.execute("INSERT INTO table ...", values)
    await db.execute("UPDATE table ...", values)
```

## Configuration Management

### Environment Variables

All configuration in `.env`:
```env
# Database
DATABASE_PATH=/path/to/db.db

# API Keys
GEMINI_API_KEY=your-key
AWS_ACCESS_KEY_ID=your-key
AWS_SECRET_ACCESS_KEY=your-secret

# Settings
DEBUG=True
LOG_LEVEL=DEBUG
```

### Adding New Config

1. Update `src/config.py`:
   ```python
   class Settings(BaseSettings):
       my_setting: str = Field(..., alias="MY_SETTING")
   ```

2. Update `env.example`:
   ```env
   MY_SETTING=default-value
   ```

## Debugging

### Enable Debug Mode

```env
DEBUG=True
LOG_LEVEL=DEBUG
```

### VS Code Launch Configuration

`.vscode/launch.json`:
```json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Python: FastAPI",
            "type": "python",
            "request": "launch",
            "module": "uvicorn",
            "args": [
                "src.main:app",
                "--reload",
                "--port",
                "8000"
            ],
            "jinja": true,
            "justMyCode": false
        }
    ]
}
```

### Logging

**View logs:**
```python
from loguru import logger

logger.debug("Debug message")
logger.info("Info message")
logger.warning("Warning message")
logger.error("Error message")
```

**Log HTTP requests:**
All requests automatically logged with correlation IDs.

## Common Tasks

### Export OpenAPI Spec
```bash
python scripts/export_openapi_spec.py
```

### Run Litestream Locally
```bash
bash scripts/start_litestream_local.sh
```

### Update Dependencies
```bash
# Update all packages
pip install -U -r requirements.txt

# Update specific package
pip install -U package-name

# Freeze new versions
pip freeze > requirements.txt
```

### Clear Cache
```python
from src.core.cache import cache
cache.clear()
```

## Best Practices

### Code Style

- Follow PEP 8
- Use type hints
- Write docstrings
- Keep functions small and focused
- Use async/await for I/O operations

### Error Handling

```python
from src.core.exceptions import NotFoundException

# Raise custom exceptions
raise NotFoundException("Resource not found", resource_id=id)

# Handle exceptions
try:
    result = await service.do_something()
except NotFoundException:
    # Handle specific error
    pass
```

### Testing

- Write tests for all new features
- Aim for >80% code coverage
- Use fixtures for common setup
- Mock external services
- Test error cases

### Security

- Never commit secrets
- Validate all user input
- Use parameterized queries
- Sanitize file uploads
- Rate limit all endpoints

### Performance

- Use caching for frequently accessed data
- Implement pagination for large datasets
- Use connection pooling
- Profile slow endpoints
- Monitor metrics

## Troubleshooting

### Common Issues

**Import errors:**
```bash
# Ensure you're in virtual environment
source venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt
```

**Database locked:**
```bash
# Check for hanging connections
# Restart application
# Verify connection pool settings
```

**Port already in use:**
```bash
# Kill process on port 8000
lsof -ti:8000 | xargs kill -9

# Or use different port
uvicorn src.main:app --reload --port 8001
```

**Tests failing:**
```bash
# Clear pytest cache
rm -rf .pytest_cache

# Run with verbose output
pytest -vv
```

## Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [SQLite Documentation](https://www.sqlite.org/docs.html)
- [Google Gemini API](https://ai.google.dev/docs)
- [Litestream Documentation](https://litestream.io/)
