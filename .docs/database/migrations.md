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
| `0004_add_email_verification_and_password_reset_tokens` | Add hashed-at-rest single-use token tables for mandatory email verification and password reset (SHA-256 hex digests of 256-bit URL-safe tokens; unique `token_hash`, `expires_at`, nullable `used_at`, indexes on `user_id` and `token_hash`, FK cascade to `users`). | `email_verification_tokens`, `password_reset_tokens` | Docs complete; NOT implemented (BE-19) |
| `0005_add_usage_daily` | Add the daily AI usage aggregate table (unique `[user_id, date, provider, model]`, upsert-increment counters for `request_count`, `input_tokens`, `output_tokens`; FK cascade to `users`). | `usage_daily` | Docs complete; NOT implemented (BE-20) |
| `0006_language_consent_and_quiz_history` | Add `user_settings.ui_language` (VARCHAR(10) NOT NULL DEFAULT 'vi') and `user_settings.personalization_consent` (BOOLEAN NOT NULL DEFAULT FALSE); add `quiz_records.submitted_at` (TIMESTAMPTZ NULL) and `quiz_records.page_title` (VARCHAR(500) NULL); add indexes `idx_quiz_records_user_created (user_id, created_at DESC)` and `idx_quiz_records_user_score (user_id, score)`. Additive columns/indexes only; no data backfill required (`total_questions` remains derived from the existing JSONB payload). | `user_settings`, `quiz_records` | Docs complete; NOT implemented (BE-23, BE-22) |
| `0007_drop_reading_history_bookmark` | Drop the unused `reading_history.is_bookmarked` column (bookmarks are not a backend feature). Destructive-but-safe: the column is dropped with its default; no other table or index changes. Downgrade re-adds the column (`BOOLEAN NOT NULL DEFAULT FALSE`). | `reading_history` | Docs complete; NOT implemented (BE-26) |
| `0008_admin_audit_and_user_search` | Add the `admin_audit_logs` table (UUID PK, `actor_user_id` FK users cascade, nullable `target_user_id` FK users set-null, `action` VARCHAR(50), `details` JSONB, nullable `request_id`, `created_at`; indexes `(actor_user_id, created_at DESC)` and `(target_user_id)`). Fully additive — new table only; the §9.2 `search` ILIKE parameter needs no schema change. | `admin_audit_logs` | Docs complete; NOT implemented (BE-27) |

Revisions are implemented in `alembic/versions/0001_initial_schema_create_all_twelve_tables.py` and `alembic/versions/0002_add_domain_blacklist_gin_idx.py`. Applied to the local project PostgreSQL instance on 2026-11-21; `alembic check` reports no metadata drift. The initial phase did not execute downgrade tests for these two revisions; the later `0003_highlight_url_digest` upgrade/downgrade verification is recorded below. Never edit an applied/shared revision to change schema; add a new revision instead.


## 2026-11-21 — Bound highlight URL index entries

- **Revision**: `0003_highlight_url_digest`, following `0002_domain_blacklist`.
- **File**: `alembic/versions/0003_bound_highlight_url_index.py`.
- **Change**: Replace `idx_highlights_user_url(user_id, page_url)` with `(user_id, md5(page_url))`. Highlight queries use digest equality plus full URL equality; stored URLs and ownership remain unchanged.
- **Reason**: Valid URLs up to 8,192 characters can exceed PostgreSQL B-tree entry limits when indexed in full, producing a database error on save.
- **Application**: Run `.venv/bin/alembic upgrade head` against the intended database before serving the updated application. Earlier revisions are unchanged.
- **Rollback**: Downgrade restores the old full-URL index. Export/remove URLs that cannot fit the old index before rollback; otherwise PostgreSQL rejects index creation and the migration transaction rolls back. The automated runner exercises upgrade → downgrade → upgrade on disposable storage before application tests; it does not attempt to fit new long URLs into the old index.


## Planned — Email verification, password reset and usage tables (BE-19 / BE-20, NOT yet implemented)

- **Revisions**: `0004_add_email_verification_and_password_reset_tokens`, then `0005_add_usage_daily` (BE-20 depends only on `0004` ordering, not its content).
- **Design**: Both token tables store exclusively SHA-256 hex digests of 256-bit URL-safe random tokens (`secrets.token_urlsafe(32)`); the plaintext token exists only inside the emailed verification/reset link and is never persisted, logged or echoed in responses. `expires_at` enforces the configured TTL (`VERIFICATION_TOKEN_TTL_HOURS` = 24h, `PASSWORD_RESET_TOKEN_TTL_MINUTES` = 60 minutes); `used_at` enforces single use.
- **Application**: Generate with `alembic revision --autogenerate` after adding the ORM models, review the generated file, and apply with `alembic upgrade head`. Both revisions are additive (new tables plus FK/indexes); downgrade drops only the created tables and must be tested with `alembic downgrade -1` before application.
- **Status**: Documented contract only. No migration file exists yet; see `.docs/development/tasks.md` (BE-19, BE-20).


## Planned — Language settings, personalization consent and quiz history (BE-21 / BE-22 / BE-23, NOT yet implemented)

- **Revision**: `0006_language_consent_and_quiz_history`, following `0005_add_usage_daily`. Ordering only requires `0001`; it can be generated after `0004`/`0005` regardless of which of those lands first.
- **Design**: Fully additive — two nullable-safe columns on `user_settings` (`ui_language VARCHAR(10) NOT NULL DEFAULT 'vi'`, `personalization_consent BOOLEAN NOT NULL DEFAULT FALSE`), two nullable columns on `quiz_records` (`submitted_at TIMESTAMPTZ NULL`, `page_title VARCHAR(500) NULL`), and two B-tree indexes on `quiz_records` (`(user_id, created_at DESC)` for history pagination/date filtering, `(user_id, score)` for stats aggregates). No data backfill: existing rows take the defaults/NULLs, and `total_questions` stays derived from `questions_payload` JSONB. No whitelist or new domain table is introduced (domain blacklist remains the only domain-level control).
- **Application**: Generate with `alembic revision --autogenerate` after updating the ORM models, review the generated file, and apply with `alembic upgrade head`. Downgrade drops only the added columns/indexes and must be tested with `alembic downgrade -1` before application.
- **Status**: Documented contract only. No migration file exists yet; see `.docs/development/tasks.md` (BE-21, BE-22, BE-23) and ADR-017.


## Planned — Drop `reading_history.is_bookmarked` (BE-26, NOT yet implemented)

- **Revision**: `0007_drop_reading_history_bookmark`, following `0006_language_consent_and_quiz_history` (ordering only requires `0001`; it can be generated after `0004`–`0006` regardless of which of those lands first).
- **Design**: Remove the `is_bookmarked BOOLEAN NOT NULL DEFAULT FALSE` column from `reading_history`. The flag was never exposed by any API endpoint or sync payload (Feature J covers conversations, highlights and settings only), so no client-visible contract changes. Downgrade re-adds the column with the original definition; no data can be restored after the drop (values were uniformly `FALSE`).
- **Application**: Update the `ReadingHistory` ORM model first (remove the attribute), generate with `alembic revision --autogenerate`, review the generated file, and apply with `alembic upgrade head`. Downgrade must be tested with `alembic downgrade -1` before application.
- **Status**: Documented contract only. No migration file exists yet; see `.docs/development/tasks.md` (BE-26), `.docs/database/schema.md` §2.8 and `.docs/api/endpoints.md` §7.3a–§7.9a. No new tables are introduced for comprehension insights — those aggregates are computed on-the-fly (ADR-018).


## Planned — Admin audit trail table (BE-27, NOT yet implemented)

- **Revision**: `0008_admin_audit_and_user_search`, following `0007_drop_reading_history_bookmark` (ordering only requires `0001`; it can be generated after `0004`–`0007` regardless of which of those lands first).
- **Design**: One new append-only table `admin_audit_logs` (see `.docs/database/schema.md` §2.16): `actor_user_id` FK -> `users.id` (ON DELETE CASCADE), nullable `target_user_id` FK -> `users.id` (ON DELETE SET NULL, nullable because CLI-wide actions have no single target), `action VARCHAR(50) NOT NULL` (e.g. `user_status_changed`, `password_reset_link_sent`, `role_promoted_cli`), `details JSONB NOT NULL DEFAULT '{}'` (e.g. old/new status), nullable `request_id VARCHAR(64)` for HTTP correlation (NULL on CLI rows), and `created_at`. Indexes `(actor_user_id, created_at DESC)` and `(target_user_id)`. Fully additive — no existing table, column or index changes; the §9.2 `search` parameter is query-level only. Documented **retention is 90 days**, enforced by a cleanup job planned for a later task (not part of BE-27 scope).
- **Application**: Add the `AdminAuditLog` ORM model, generate with `alembic revision --autogenerate`, review the generated file, and apply with `alembic upgrade head`. Downgrade drops only the new table and must be tested with `alembic downgrade -1` before application.
- **Status**: Documented contract only. No migration file exists yet; see `.docs/development/tasks.md` (BE-27), `.docs/database/schema.md` §2.16, `.docs/api/endpoints.md` §9.3, §9.5, §9.6 and ADR-020.
