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

## 3. Migration Log

| Revision ID | Description | Impacted Tables | Status |
|---|---|---|---|
| `0001_initial_schema` | Full initial schema across all 12 core tables (`users`, `oauth_accounts`, `auth_sessions`, `refresh_tokens`, `user_api_keys`, `user_settings`, `conversations`, `messages`, `reading_history`, `highlights`, `quiz_records`, `ai_feedback`) including session lifecycle/revocation fields, `users.sync_clock`, `role`, `status`, and sync indexes. | All 12 tables | Implemented; applied locally |
| `0002_domain_blacklist` | Add PostgreSQL GIN index on `user_settings.blacklisted_domains` for high-speed domain matching. | `user_settings` | Implemented; applied locally |
| `0003_highlight_url_digest` | Replace full URL index with bounded digest expression and exact URL filtering. | `highlights` | Upgrade/downgrade/upgrade verified on disposable PostgreSQL; apply to the project database with `alembic upgrade head` |

Revisions are implemented in `alembic/versions/0001_initial_schema_create_all_twelve_tables.py` and `alembic/versions/0002_add_domain_blacklist_gin_idx.py`. Applied to the local project PostgreSQL instance on 2026-11-21; `alembic check` reports no metadata drift. The initial phase did not execute downgrade tests for these two revisions; the later `0003_highlight_url_digest` upgrade/downgrade verification is recorded below. Never edit an applied/shared revision to change schema; add a new revision instead.


## 2026-11-21 — Bound highlight URL index entries

- **Revision**: `0003_highlight_url_digest`, following `0002_domain_blacklist`.
- **File**: `alembic/versions/0003_bound_highlight_url_index.py`.
- **Change**: Replace `idx_highlights_user_url(user_id, page_url)` with `(user_id, md5(page_url))`. Highlight queries use digest equality plus full URL equality; stored URLs and ownership remain unchanged.
- **Reason**: Valid URLs up to 8,192 characters can exceed PostgreSQL B-tree entry limits when indexed in full, producing a database error on save.
- **Application**: Run `.venv/bin/alembic upgrade head` against the intended database before serving the updated application. Earlier revisions are unchanged.
- **Rollback**: Downgrade restores the old full-URL index. Export/remove URLs that cannot fit the old index before rollback; otherwise PostgreSQL rejects index creation and the migration transaction rolls back. The automated runner exercises upgrade → downgrade → upgrade on disposable storage before application tests; it does not attempt to fit new long URLs into the old index.
