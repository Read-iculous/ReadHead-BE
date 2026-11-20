# Development Commands Reference

## 1. Server Execution
```bash
# Start server with hot reload (dev mode)
uvicorn app.main:app --reload --port 8000

# Start server with verbose logging
uvicorn app.main:app --reload --log-level debug

# Production start with multiple workers
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

## 2. Database & Migrations (Alembic)
```bash
# Generate a new migration revision based on model changes
alembic revision --autogenerate -m "descriptive_name"

# Apply all pending migrations to the latest revision
alembic upgrade head

# Rollback the last migration
alembic downgrade -1

# Show current database revision
alembic current

# Show migration history
alembic history --verbose
```

## 3. Testing (Pytest)
```bash
# Run all tests
pytest

# Run tests with verbose output and print statements
pytest -v -s

# Run tests with test coverage report
pytest --cov=app --cov-report=term-missing --cov-report=html

# Run unit tests only
pytest tests/unit/

# Run integration tests only
pytest tests/integration/

# Run a single test file
pytest tests/integration/test_auth_api.py -v
```

## 4. Code Quality, Formatting & Linting
```bash
# Format code with Black
black app/ tests/

# Sort imports with isort
isort app/ tests/

# Check formatting without modifying files
black --check app/ tests/
isort --check-only app/ tests/

# Run Ruff linter
ruff check app/ tests/

# Run static type checking with Mypy
mypy app/
```

## 5. Security & Maintenance Utilities
```bash
# Rotate master encryption key for stored BYOK user keys (upgrades v1 -> v2)
python -m app.cli.rotate_keys --old-key <old_master_key> --new-key <new_master_key>
```
