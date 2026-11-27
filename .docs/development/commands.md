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
# Bootstrap the initial Super Admin account
python -m app.cli.create_admin --email admin@readhead.io --password "SecureAdminPassword123!"

# Rotate master encryption key for stored BYOK user keys (upgrades v1 -> v2)
python -m app.cli.rotate_keys --old-version v1 --new-version v2

# Purge soft-deleted tombstones older than 30 days (cascades to messages & feedback)
python -m app.cli.purge_tombstones --days 30
```

## 6. Docker & Infrastructure Services
```bash
# Start PostgreSQL 15 and Redis 7 in the background
docker compose up -d

# Check status and health of backend services
docker compose ps

# View logs from running containers
docker compose logs -f

# Stop services preserving database volumes
docker compose down

# Stop services and remove volumes (clean reset)
docker compose down -v
```

### Zero-Downtime Rotation Runbook
1. Distribute `ENCRYPTION_MASTER_KEYS` containing both `v1` and `v2` to every API worker and maintenance process. Keep `CURRENT_KEY_VERSION=v1` until every process can decrypt both versions.
2. Roll out `CURRENT_KEY_VERSION=v2` to **all writers** and confirm no old-version writer remains. Keep both keys available; existing `v1` records remain readable.
3. Run `python -m app.cli.rotate_keys --old-version v1 --new-version v2`. Process bounded batches. Each update uses a compare-and-swap on record ID and the exact original ciphertext (`WHERE id = :id AND encrypted_key = :original_ciphertext`), so a concurrent user key replacement is never overwritten. Skip/re-read changed rows; resume safely after interruption. Cipher-only re-encryption does not change user-visible metadata.
4. Verify every active writer still uses `v2`, no database row has a `v1:` prefix, and a second scan finds zero remaining `v1` rows. Only then remove `v1` from live keyrings. Retain old key material securely for the backup-restore retention policy; restoring an old backup requires its matching key.
5. On migration failure keep the dual keyring and continue serving reads/writes with `v2`; resume migration. Never remove a key still referenced by a record. Rolling back a writer to `v1` invalidates the completion check and requires another migration scan.
