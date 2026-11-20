# Coding Conventions

## 1. Python Style Guide
- **Python Version**: 3.10+
- **Formatting**: `black` with 88 character line limit.
- **Imports**: Sorted using `isort` with 3 sections: Standard Library -> Third-party -> Local Application.
- **Type Annotations**: Mandatory on all function arguments and return types. Use modern syntax: `list[str]` instead of `List[str]`, `str | None` instead of `Optional[str]`.

## 2. Naming Standards
| Item | Convention | Example |
|---|---|---|
| Modules / Files | `snake_case` | `api_key_service.py`, `conversation.py` |
| Classes (Models, Schemas) | `PascalCase` | `User`, `ApiKeyCreate`, `ConversationResponse` |
| Functions & Methods | `snake_case` | `get_user_by_id`, `encrypt_key` |
| Constants | `SCREAMING_SNAKE_CASE` | `DEFAULT_PAGE_SIZE`, `MAX_TOKEN_LENGTH` |
| API Endpoints | `kebab-case` nouns, plural | `/api/v1/api-keys`, `/api/v1/conversations` |

## 3. Layer Separation Rules
1. **Routers (`app/routers/`)**:
   - Only handle query/body deserialization, dependency injection, service invocation, and status/response formatting.
   - **Never** call `db.execute()`, `db.add()`, or ORM query helpers directly.
   - **Never** perform encryption, LLM calls, or raw business calculations.
2. **Services (`app/services/`)**:
   - Encapsulate all business rules, orchestration, transaction boundaries, and provider communications.
   - Raise custom exceptions from `app.core.exceptions` instead of returning raw error dictionaries.
3. **Schemas (`app/schemas/`)**:
   - Pure Pydantic models. Use `model_config = ConfigDict(from_attributes=True)` for ORM mapping.
   - Never import from `app.services` or `app.routers`.
4. **Models (`app/models/`)**:
   - Declarative SQLAlchemy models. Define table names, columns, indexes, foreign keys, and relationships.
   - No business logic inside models.

## 4. Async & Database Best Practices
- Every database interaction must be async: `await db.execute(...)`.
- Always use `db.scalars().all()` or `db.scalar(...)` instead of raw tuples.
- Never use blocking libraries (e.g., standard `requests`, `time.sleep`) in route handlers or services. Always use `httpx.AsyncClient` and `asyncio.sleep`.
