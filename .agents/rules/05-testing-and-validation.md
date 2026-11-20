# 05 — Testing and Validation

## Testing Philosophy
- **No code is complete without tests**
- Tests must run independently and not depend on each other
- Tests must cover both happy paths and error cases

## Test Directory Structure
```
tests/
├── conftest.py           ← Shared fixtures (DB session, test client, auth headers)
├── unit/
│   ├── services/
│   │   └── test_user_service.py
│   └── schemas/
│       └── test_user_schemas.py
└── integration/
    ├── test_users_api.py
    └── test_books_api.py
```

## Test Naming Convention
```python
# Pattern: test_<function>_<scenario>_<expected_result>
def test_create_user_valid_data_returns_201(): ...
def test_create_user_duplicate_email_raises_409(): ...
def test_get_user_nonexistent_id_raises_404(): ...
def test_list_users_empty_db_returns_empty_list(): ...
```

## Test Categories

### Unit Tests (`tests/unit/`)
- Test each service function in isolation
- Mock the DB session and external dependencies
- Fast, no real database needed

```python
async def test_get_user_by_id_found(mock_db):
    # Arrange
    mock_user = User(id=1, email="test@example.com")
    mock_db.get.return_value = mock_user

    # Act
    result = await user_service.get_user_by_id(user_id=1, db=mock_db)

    # Assert
    assert result.id == 1
    assert result.email == "test@example.com"
```

### Integration Tests (`tests/integration/`)
- Test the full HTTP flow from endpoint to DB
- Use a real test database (SQLite in-memory or a PostgreSQL test instance)
- Use FastAPI's `TestClient` or `AsyncClient`

```python
async def test_create_user_endpoint(client, db_session):
    response = await client.post("/users", json={
        "email": "new@example.com",
        "password": "securepassword"
    })
    assert response.status_code == 201
    assert response.json()["data"]["email"] == "new@example.com"
```

## Coverage Requirements
- Service layer: **≥ 80% coverage**
- Router layer: **≥ 70% coverage** (via integration tests)
- Schemas: Pydantic validates itself — test validation edge cases only

## Test Commands
```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=app --cov-report=html

# Run unit tests only
pytest tests/unit/

# Run a specific file
pytest tests/integration/test_users_api.py -v
```

## Validation Before Completing a Task
Before reporting a task as done, the agent must:
1. Run `pytest` — all tests must pass
2. Run `black --check app/` — formatting must be clean
3. Run `mypy app/` — type checks must pass (if installed)
4. Confirm no `print()` or debug code remains

## Standard Fixtures (to be created in `conftest.py`)
```python
@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]: ...

@pytest.fixture
async def client(db_session) -> AsyncGenerator[AsyncClient, None]: ...

@pytest.fixture
async def auth_headers(client) -> dict: ...  # Token for a regular test user

@pytest.fixture
async def admin_headers(client) -> dict: ...  # Token for an admin test user
```
