# Recommended Additional Ruff Rules for Code Quality

## Current Status
You already have **excellent** coverage with 18 rule categories enabled. Here are **high-value additions** to consider:

---

## 🔥 Highly Recommended (Add These)

### 1. **ASYNC** - Async best practices
```toml
"ASYNC",  # flake8-async
```

**What it catches**:
- `ASYNC100` - Blocking HTTP calls in async functions
- `ASYNC101` - `open()` in async functions (use `aiofiles`)
- `ASYNC102` - Blocking `sleep()` in async functions
- `ASYNC109` - Async function with no `await`
- `ASYNC110` - Potential blocking I/O in async function

**Why add it**: You're using FastAPI (async framework) - this catches async/await mistakes that can kill performance.

**Example caught**:
```python
async def fetch_data():
    time.sleep(5)  # ❌ ASYNC102 - Should use asyncio.sleep()
    return requests.get(url)  # ❌ ASYNC100 - Should use httpx/aiohttp
```

---

### 2. **FBT** - Boolean trap prevention
```toml
"FBT",   # flake8-boolean-trap
```

**What it catches**:
- `FBT001` - Boolean positional argument in function definition
- `FBT002` - Boolean default value in function definition
- `FBT003` - Boolean positional value in function call

**Why add it**: Prevents confusing function calls like `process(True, False, True)`.

**Example caught**:
```python
# Bad - What do these booleans mean?
def send_email(to, subject, body, urgent, cc_admin):  # ❌ FBT001

# Good - Use explicit parameters
def send_email(to, subject, body, *, priority="normal", cc_admin=False):  # ✅
```

You may want to ignore some cases:
```toml
"FBT002",  # Allow boolean default values (common in APIs)
```

---

### 3. **PERF** - Performance anti-patterns
```toml
"PERF",  # Perflint
```

**What it catches**:
- `PERF101` - Unnecessary list cast
- `PERF102` - Inefficient list comprehension
- `PERF203` - Try-except in loop (should be outside)
- `PERF401` - Manual list comprehension (use list comp)
- `PERF402` - Manual list extend (use `list.extend()`)

**Why add it**: Catches common Python performance mistakes.

**Example caught**:
```python
# Bad - Try-except inside loop
for item in items:
    try:  # ❌ PERF203
        process(item)
    except ValueError:
        pass

# Good - Try-except outside loop
try:  # ✅
    for item in items:
        process(item)
except ValueError:
    pass
```

---

### 4. **FURB** - Modern Python refactoring suggestions
```toml
"FURB",  # refurb
```

**What it catches**:
- `FURB103` - Use `write_text()`/`read_text()` instead of open
- `FURB105` - Use `print(..., file=)` instead of `sys.stdout.write()`
- `FURB110` - Use `if any(...)` instead of `for` with `break`
- `FURB113` - Use `extend()` instead of repeated `append()`
- `FURB116` - Use `int()` instead of `math.floor()`

**Why add it**: Encourages more Pythonic, readable code.

**Example caught**:
```python
# Bad
with open("file.txt") as f:  # ❌ FURB103
    content = f.read()

# Good
content = Path("file.txt").read_text()  # ✅
```

---

### 5. **SLOT** - Enforce `__slots__` for memory efficiency
```toml
"SLOT",  # flake8-slots
```

**What it catches**:
- `SLOT000` - Missing `__slots__` in subclass
- `SLOT001` - Missing `__slots__` in class

**Why add it**: Reduces memory usage for classes with many instances (like your `Message`, `Conversation` models).

**Example**:
```python
# Before
class Message:
    def __init__(self, id, content):
        self.id = id
        self.content = content

# After - 30-40% memory savings for many instances
class Message:
    __slots__ = ('id', 'content')  # ✅ SLOT001
    
    def __init__(self, id, content):
        self.id = id
        self.content = content
```

---

### 6. **LOG** - Logging best practices
```toml
"LOG",   # flake8-logging
```

**What it catches**:
- `LOG001` - Use `logging.getLogger(__name__)` not `logging.getLogger()`
- `LOG002` - Invalid `logging` level
- `LOG007` - Use `exception()` not `error()` in except block
- `LOG009` - Redundant `exc_info` in `logging.exception()`

**Why add it**: You use `loguru`, but if you ever use standard `logging`, this catches mistakes.

---

### 7. **FA** - Future annotations (Python 3.7+)
```toml
"FA",    # flake8-future-annotations
```

**What it catches**:
- `FA100` - Missing `from __future__ import annotations`
- `FA102` - Missing future annotations but using forward references

**Why add it**: Enables cleaner type hints and deferred evaluation.

**Example**:
```python
from __future__ import annotations  # ✅ FA100

# Now you can use forward references without quotes
def process(items: list[Item]) -> Item:  # Instead of list['Item']
    ...
```

---

## 🎯 Consider Adding (Task-Specific)

### 8. **DJ** - Django-specific (if you add Django admin)
```toml
"DJ",    # flake8-django
```
Skip for now unless you add Django.

---

### 9. **NPY** - NumPy-specific (if you add ML features)
```toml
"NPY",   # NumPy-specific rules
```
Skip for now unless you add NumPy/ML.

---

### 10. **PD** - Pandas-specific (if you add data analytics)
```toml
"PD",    # pandas-vet
```
Skip for now unless you add Pandas.

---

### 11. **FAST** - FastAPI-specific rules
```toml
"FAST",  # fastapi-code-generator
```
Currently experimental, but worth watching for FastAPI-specific best practices.

---

## 🔧 Recommended Configuration Update

```toml
[tool.ruff.lint]
select = [
    # Current rules (keep these)
    "E",      # pycodestyle errors
    "W",      # pycodestyle warnings
    "F",      # pyflakes
    "I",      # isort
    "C",      # flake8-comprehensions
    "B",      # flake8-bugbear
    "UP",     # pyupgrade
    "N",      # pep8-naming
    "S",      # bandit (security)
    "A",      # flake8-builtins
    "COM",    # flake8-commas
    "DTZ",    # flake8-datetimez
    "EM",     # flake8-errmsg
    "G",      # flake8-logging-format
    "PIE",    # flake8-pie
    "T20",    # flake8-print
    "PT",     # flake8-pytest-style
    "Q",      # flake8-quotes
    "RET",    # flake8-return
    "SIM",    # flake8-simplify
    "TID",    # flake8-tidy-imports
    "TCH",    # flake8-type-checking
    "ARG",    # flake8-unused-arguments
    "PTH",    # flake8-use-pathlib
    "ERA",    # eradicate
    "PL",     # pylint
    "TRY",    # tryceratops
    "RUF",    # ruff-specific rules
    
    # NEW RECOMMENDED ADDITIONS
    "ASYNC",  # async best practices (HIGH PRIORITY for FastAPI)
    "FBT",    # boolean trap prevention
    "PERF",   # performance anti-patterns
    "FURB",   # modern Python refactoring
    "SLOT",   # memory optimization with __slots__
    "LOG",    # logging best practices
    "FA",     # future annotations
]

ignore = [
    # Keep your existing ignores
    "S101",    # Use of assert detected (needed for tests)
    "TRY003",  # Avoid specifying long messages outside exception class
    "EM101",   # Exception must not use string literal
    "EM102",   # Exception must not use f-string literal
    "G004",    # Logging statement uses f-string
    "PLR0913", # Too many arguments to function call
    "S104",    # Possible binding to all interfaces
    "DTZ005",  # datetime.now() without tzinfo
    "COM812",  # Missing trailing comma (conflicts with formatter)
    "PLR2004", # Magic value used in comparison (common in tests)
    "W293",    # Blank line contains whitespace
    "PT003",   # Pytest scope is implied
    "ARG001",  # Unused function argument (pytest fixtures)
    "ARG002",  # Unused method argument
    "TRY300",  # Consider moving to else block
    "B904",    # Use raise from for exception chaining
    "PLC0415", # Import should be at top-level (intentional for circular import avoidance)
    "SIM105",  # Use contextlib.suppress
    "S110",    # try-except-pass detected
    "C901",    # Function is too complex (can address in refactoring)
    "RUF013",  # PEP 484 prohibits implicit Optional
    "E501",    # Line too long (black handles this)
    
    # NEW IGNORES (if needed after adding rules)
    "FBT002",  # Allow boolean default values (common in FastAPI)
    "FBT003",  # Allow boolean positional values in calls (common patterns)
    "PERF203", # Allow try-except in loop for specific cases
    "SLOT000", # Don't enforce __slots__ everywhere (only where beneficial)
]
```

---

## 📊 Impact Assessment

### High Impact (Add First)
1. **ASYNC** - Critical for async FastAPI app
2. **PERF** - Easy wins for performance
3. **FURB** - Improves code readability

### Medium Impact (Add Soon)
4. **FBT** - Improves API clarity
5. **FA** - Better type hints
6. **LOG** - Better logging (if you switch from loguru)

### Low Impact (Consider Later)
7. **SLOT** - Memory optimization (only if needed)

---

## 🚀 Implementation Strategy

### Phase 1: Run with new rules to see violations
```bash
ruff check src/ tests/ --select ASYNC,PERF,FURB --config pyproject.toml
```

### Phase 2: Fix or ignore specific violations
```bash
# Fix the easy ones
ruff check src/ tests/ --select ASYNC,PERF,FURB --fix

# Add specific ignores for intentional patterns
```

### Phase 3: Add to pyproject.toml
```bash
# Update select list in pyproject.toml
# Run full check
ruff check src/ tests/
```

---

## 📝 Expected Findings

Based on your codebase, you'll likely find:

### ASYNC violations
- `gemini_client.py` - May have blocking calls in async functions
- `storage_service.py` - File I/O in async context

### PERF violations
- Loop optimizations in message processing
- List comprehension improvements

### FURB violations
- Path operations that could use pathlib methods
- Modernization suggestions

### FBT violations
- Boolean parameters in API endpoints
- Configuration flags

---

## 🎓 Learning Resources

- **Ruff Rules**: https://docs.astral.sh/ruff/rules/
- **ASYNC rules**: https://docs.astral.sh/ruff/rules/#flake8-async-async
- **PERF rules**: https://docs.astral.sh/ruff/rules/#perflint-perf
- **FURB rules**: https://docs.astral.sh/ruff/rules/#refurb-furb

---

## Summary

**Top 3 to add right now**:
1. ✅ **ASYNC** - Critical for FastAPI performance
2. ✅ **PERF** - Easy performance wins
3. ✅ **FURB** - Better Python patterns

**Total potential new rules**: 7 categories, ~200 additional checks

Your code quality setup is already **excellent**. These additions will take it to **exceptional** level! 🚀
