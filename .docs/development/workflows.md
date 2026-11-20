# Development Workflows

## 1. Feature Development Workflow
Follow this disciplined cycle for every feature:
1. **Scope & Research**:
   - Check `.docs/api/endpoints.md` and `.docs/database/schema.md`.
   - Activate the `feature-implementation` or `api-endpoint-implementation` skill.
2. **Schema & Model First**:
   - Define Pydantic request/response schemas in `app/schemas/`.
   - Update SQLAlchemy models in `app/models/` if new tables or columns are needed.
   - Run `alembic revision --autogenerate -m "..."` and `alembic upgrade head`.
3. **Service Layer Implementation**:
   - Implement business logic in `app/services/`.
   - Handle exceptions by raising domain exceptions.
4. **Router & Route Binding**:
   - Create router handler in `app/routers/` injecting `db: AsyncSession = Depends(get_db)`.
   - Register the router in `app/routers/router.py`.
5. **Testing**:
   - Write integration tests in `tests/integration/` testing both 200/201 and 4xx failure scenarios.
   - Run `pytest` to verify all tests pass.
6. **Documentation Sync**:
   - Run the `documentation-sync` skill to record the new endpoint or schema changes in `.docs/`.

---

## 2. Adding a New AI Provider Workflow
When adding support for a new LLM provider (e.g. Mistral, DeepSeek, Ollama):
1. Create a new provider adapter in `app/core/ai/<provider>_adapter.py` implementing `BaseAIProvider`.
2. Register the adapter in `ProviderFactory` (`app/core/ai/factory.py`).
3. Add the provider identifier string to `app/schemas/api_key.py` and `app/models/api_key.py`.
4. Add unit test for the adapter mocking external HTTP responses.
5. Update `.docs/technical/tech-stack.md` and `.docs/api/endpoints.md`.
