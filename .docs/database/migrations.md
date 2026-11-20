# Database Migrations

## 1. Migration Strategy with Alembic
ReadHead-BE uses **Alembic** to manage all PostgreSQL schema evolutions.

### Golden Rules
1. **Never edit an existing applied migration**: Once merged and applied to staging or production, migration revisions are immutable. Create a new revision to alter or roll back changes.
2. **Always test both Upgrade and Downgrade**: Every migration script must implement a reversible `downgrade()` function and be tested locally via `alembic downgrade -1`.
3. **Synchronize ORM Models first**: Always update `app/models/` classes before running `alembic revision --autogenerate`.

---

## 2. Standard Migration Workflow

```bash
# 1. Update ORM models in app/models/
# 2. Generate a new revision
alembic revision --autogenerate -m "create_initial_schema"

# 3. Review the generated file in alembic/versions/
# 4. Apply migration to the database
alembic upgrade head

# 5. Verify current database head
alembic current
```

---

## 3. Migration Log (Planned Sequence)

| Revision ID | Description | Impacted Tables | Status |
|---|---|---|---|
| `0001_initial_schema` | Full initial schema across all 11 core tables (`users`, `oauth_accounts`, `refresh_tokens`, `user_api_keys`, `user_settings`, `conversations`, `messages`, `reading_history`, `highlights`, `quiz_records`, `ai_feedback`) including `role` and `status` columns. | All 11 tables | Planned |
| `0002_add_domain_blacklist_gin_idx` | Add PostgreSQL GIN index on `user_settings.blacklisted_domains` for high-speed domain matching. | `user_settings` | Planned |
