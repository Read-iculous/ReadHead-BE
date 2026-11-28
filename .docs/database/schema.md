# Database Schema Specification

## 1. Schema Conventions
- All table names are in `snake_case` plural (e.g. `users`, `api_keys`).
- All primary keys are `UUID` (`gen_random_uuid()`) for security and non-enumerable IDs.
- All timestamps use `TIMESTAMP WITH TIME ZONE` and default to `CURRENT_TIMESTAMP`.
- Optimistic locking columns (`version INTEGER NOT NULL DEFAULT 1`) are added to entities synchronized across devices.
- Soft delete (`is_deleted BOOLEAN NOT NULL DEFAULT FALSE`) is supported on historical user entities.

---

## 2. Table Definitions

### 2.1 `users` (Feature A & Admin Management)
Core user account registry.
| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | `UUID` | NO | `gen_random_uuid()` | Primary Key |
| `email` | `VARCHAR(255)` | NO | — | Unique user email address |
| `hashed_password` | `VARCHAR(255)` | YES | NULL | Salted bcrypt hash (NULL for OAuth-only users) |
| `full_name` | `VARCHAR(150)` | YES | NULL | Display name |
| `avatar_url` | `TEXT` | YES | NULL | Profile image URL |
| `role` | `VARCHAR(20)` | NO | `'user'` | User authorization role: `'user'`, `'admin'` |
| `status` | `VARCHAR(20)` | NO | `'active'` | Account status: `'active'`, `'suspended'`, `'banned'` |
| `is_active` | `BOOLEAN` | NO | `TRUE` | Whether account is active (syncs with status == 'active') |
| `is_verified` | `BOOLEAN` | NO | `FALSE` | Email verification status |
| `sync_clock` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | Server-only monotonic sync timestamp allocator/checkpoint; see ADR-013 |
| `created_at` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | Account creation timestamp |
| `updated_at` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | Last profile update timestamp |

### 2.2 `oauth_accounts` (Feature A)
Linked third-party OAuth identities (Google, GitHub).
| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | `UUID` | NO | `gen_random_uuid()` | Primary Key |
| `user_id` | `UUID` | NO | — | FK -> `users.id` (ON DELETE CASCADE) |
| `provider` | `VARCHAR(50)` | NO | — | `google`, `github` |
| `provider_user_id` | `VARCHAR(255)` | NO | — | Unique ID from OAuth provider |
| `created_at` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | Linked timestamp |
*(Unique Constraint: `[provider, provider_user_id]`)*

### 2.3 `refresh_tokens` (Feature A)
Tracks refresh-token chains owned by `auth_sessions`; only SHA-256 token hashes are persisted.
| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | `UUID` | NO | `gen_random_uuid()` | Primary Key |
| `user_id` | `UUID` | NO | — | FK -> `users.id` (ON DELETE CASCADE) |
| `session_id` | `UUID` | NO | — | FK -> `auth_sessions.id`; shared across rotation chain |
| `token_hash` | `VARCHAR(255)` | NO | — | Unique SHA-256 hash of refresh token |
| `device_info` | `VARCHAR(255)` | YES | NULL | Browser/OS user agent identifier |
| `expires_at` | `TIMESTAMPTZ` | NO | — | Expiration timestamp |
| `is_revoked` | `BOOLEAN` | NO | `FALSE` | True after rotation, logout or a security event |
| `revoked_at` | `TIMESTAMPTZ` | YES | NULL | Rotation/revocation time; required when revoked |
| `revocation_reason` | `VARCHAR(20)` | YES | NULL | `rotated`, `logout`, `security`; required when revoked |
| `replaced_by_token_id` | `UUID` | YES | NULL | Self FK -> `refresh_tokens.id` (ON DELETE SET NULL); populated on rotation |
| `created_at` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | Issued timestamp |

*(Unique `token_hash`; composite FK `[session_id, user_id]` -> `auth_sessions[id, user_id]` with ON DELETE CASCADE. `is_revoked = FALSE` requires NULL revocation fields; `TRUE` requires both timestamp and reason. Replacement tokens must belong to the same session. Retain rotated rows at least through their token expiry plus clock leeway.)*

### 2.4 `user_api_keys` (Feature C — BYOK Vault)
User-provided LLM provider API keys encrypted at rest via AES-256.
| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | `UUID` | NO | `gen_random_uuid()` | Primary Key |
| `user_id` | `UUID` | NO | — | FK -> `users.id` (ON DELETE CASCADE) |
| `provider` | `VARCHAR(50)` | NO | — | `openai`, `gemini`, `claude` |
| `encrypted_key` | `TEXT` | NO | — | Symmetrically encrypted API key (AES-256-GCM format: `<version>:<nonce>:<ciphertext>:<auth_tag>`) |
| `key_hint` | `VARCHAR(20)` | NO | — | Masked preview (e.g. `sk-...4F8a`) |
| `is_active` | `BOOLEAN` | NO | `TRUE` | Whether this key is currently selected |
| `last_validated_at`| `TIMESTAMPTZ` | YES | NULL | Last successful ping check timestamp |
| `created_at` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | Key added timestamp |
| `updated_at` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | Last updated timestamp |
*(Unique Constraint: `[user_id, provider]`)*

### 2.5 `user_settings` (Features B, G & H)
User-level configuration, accessibility profile, proactive assistance, and privacy rules.
| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | `UUID` | NO | `gen_random_uuid()` | Primary Key |
| `user_id` | `UUID` | NO | — | FK -> `users.id` (Unique, 1-to-1) |
| `default_provider` | `VARCHAR(50)` | NO | `'gemini'` | Default AI provider |
| `default_model` | `VARCHAR(100)` | NO | `'gemini-1.5-flash'` | Default AI model name |
| `target_language` | `VARCHAR(10)` | NO | `'vi'` | Preferred translation language; one of `vi`, `en`, `ja`, `zh`, `ko`, `fr`, `de`, `es` |
| `ui_language` | `VARCHAR(10)` | NO | `'vi'` | Extension UI language: `vi` or `en`; governs interface text only, separate from translation |
| `explanation_level` | `VARCHAR(20)` | NO | `'standard'` | `simple`, `standard`, `expert` |
| `accessibility_profile` | `JSONB` | NO | `'{"dyslexia_font": false, "font_size_delta": 0, "line_spacing": 1.5, "bionic_reading": false, "high_contrast": false}'` | Accessibility & page styling preferences (BG-06, BR-11) |
| `proactive_assistance_enabled`| `BOOLEAN` | NO | `TRUE` | Whether to suggest tips on reading slowdowns (Feature G) |
| `proactive_sensitivity` | `VARCHAR(20)` | NO | `'medium'` | `low`, `medium`, `high` |
| `data_protection_mode` | `BOOLEAN` | NO | `TRUE` | Feature H: Block sensitive PII/secrets outbound by default |
| `privacy_mode_enabled` | `BOOLEAN` | NO | `FALSE` | Global toggle to prevent reading history logs (see Privacy Mode Matrix below) |
| `personalization_consent` | `BOOLEAN` | NO | `FALSE` | ADR-017 opt-in for using `reading_history`/AI interactions for personalization; independent of `privacy_mode_enabled`; revocation sets FALSE without deleting stored data; re-read under the user lock before any personalization use |
| `blacklisted_domains` | `JSONB` | NO | `'[]'` | List of domain patterns to ignore (Domain Blacklist Policy; no domain whitelist exists — blacklist is the only domain-level control) |
| `version` | `INTEGER` | NO | `1` | Optimistic lock version for multi-device sync (Feature J) |
| `updated_at` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | Last settings update |

#### Privacy Mode Storage Matrix (`privacy_mode_enabled = TRUE`)
- **`reading_history`**: Strictly blocked (zero rows written; no URLs, titles, or dwell time saved).
- **`conversations` & `messages`**: Ephemeral in-session chat only (`page_url = NULL`); retained strictly in client memory (RAM/sessionStorage) and never written to PostgreSQL.
- **`highlights`**: Preserved only if user explicitly clicks "Save Highlight" (explicit user intent).
- **`ai_feedback`**: Blocked (ephemeral messages not persisted; a feedback POST referencing a private-mode message returns `404 MESSAGE_NOT_FOUND` — the FK target row does not exist).
- **`quiz_records`**: Quizzes are generated and cached temporarily in Redis (`ephemeral_quiz:{quiz_id}` with 30m TTL) for interactive grading, never written to `quiz_records` table.
- **Existing Historical Data**: Unaltered (enabling Privacy Mode does not delete past history).

Privacy checks for content writes are made under the `users` row lock shared by settings PATCH/sync, not solely from an earlier request snapshot. SSE admission and final/partial persistence re-read settings after acquiring that lock. A private request never becomes persistent later; already committed content from before the toggle remains historical data. Automatic history and generated-quiz storage follow the same ordering.

### 2.6 `conversations` (Feature I & D)
Chat sessions tied to specific reading contexts. Tab-isolated via `reading_session_id`.
| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | `UUID` | NO | `gen_random_uuid()` | Primary Key |
| `user_id` | `UUID` | NO | — | FK -> `users.id` (ON DELETE CASCADE) |
| `reading_session_id` | `UUID` | YES | NULL | Active reading session/tab UUID. Binds dynamically via `/conversations/{id}/bind`. NULL when opened in unbound mode from Dashboard |
| `title` | `VARCHAR(255)` | NO | `'New Conversation'` | Title / summary of conversation |
| `page_url` | `TEXT` | YES | NULL | Web page URL where conversation started. Set to NULL upon reading history clearance or in Privacy Mode |
| `page_title` | `VARCHAR(500)` | YES | NULL | Document / page title |
| `version` | `INTEGER` | NO | `1` | Optimistic lock & sync version. Incremented on every message, title update, soft delete, or history clearance |
| `is_deleted` | `BOOLEAN` | NO | `FALSE` | Soft delete flag (tombstone retained at least 30 days; cursor retention anchors older than 30 days trigger `410 CURSOR_EXPIRED`) |
| `created_at` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | Session start |
| `updated_at` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | Last update / message / clearance timestamp |

### 2.7 `messages` (Feature E — AI Reading Assistance)
Individual turns in a conversation with source grounding metadata.
| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | `UUID` | NO | `gen_random_uuid()` | Primary Key |
| `conversation_id` | `UUID` | NO | — | FK -> `conversations.id` (CASCADE) |
| `sender_role` | `VARCHAR(20)` | NO | — | `user`, `assistant`, `system` |
| `content` | `TEXT` | NO | — | Text content of the message |
| `selected_context` | `TEXT` | YES | NULL | User-highlighted snippet prompt was based on |
| `provider_used` | `VARCHAR(50)` | YES | NULL | Provider that generated this response |
| `model_used` | `VARCHAR(100)` | YES | NULL | Model version used |
| `is_grounded` | `BOOLEAN` | NO | `TRUE` | Whether answer is backed directly by the page (BR-12~13) |
| `uncertainty_flag` | `BOOLEAN` | NO | `FALSE` | True if AI expressed lack of evidence (BR-14) |
| `grounding_notes` | `TEXT` | YES | NULL | Citation or clarification notes |
| `created_at` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | Message timestamp |

### 2.8 `reading_history` (Feature I)
Browsed pages and reading session logs (subject to privacy mode).
| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | `UUID` | NO | `gen_random_uuid()` | Primary Key |
| `user_id` | `UUID` | NO | — | FK -> `users.id` (ON DELETE CASCADE) |
| `page_url` | `TEXT` | NO | — | Cleaned URL |
| `page_title` | `VARCHAR(500)` | YES | NULL | Title of the web page |
| `cached_summary` | `TEXT` | YES | NULL | Pre-generated summary if created |
| `reading_time_seconds` | `INTEGER` | NO | `0` | Estimated dwell/reading duration |
| `visited_at` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | Visit timestamp |
*(Index on `[user_id, visited_at DESC]`. The former `is_bookmarked` flag has been dropped — revision `0007_drop_reading_history_bookmark`; bookmarks are not a backend feature.)*

### 2.9 `highlights` (Feature I)
User-saved text selections and personal notes. Synchronized across devices.
| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | `UUID` | NO | `gen_random_uuid()` | Primary Key |
| `user_id` | `UUID` | NO | — | FK -> `users.id` (ON DELETE CASCADE) |
| `page_url` | `TEXT` | NO | — | Target page URL |
| `highlighted_text` | `TEXT` | NO | — | Raw selected text |
| `user_note` | `TEXT` | YES | NULL | Optional user comment or note |
| `color` | `VARCHAR(20)` | NO | `'yellow'` | Color code (yellow, green, blue, pink) |
| `version` | `INTEGER` | NO | `1` | Sync version (Feature J) |
| `is_deleted` | `BOOLEAN` | NO | `FALSE` | Soft delete flag |
| `created_at` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | Creation timestamp |
| `updated_at` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | Last updated timestamp (for sync cursor) |

### 2.10 `quiz_records` (Feature F — Comprehension Questions)
Stores generated quizzes, user responses, and score history. Serves the quiz-history endpoints (`GET /quiz`, `/quiz/stats`, `/quiz/{id}` — endpoints §6.3–6.5); NOT part of `/sync`.
| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | `UUID` | NO | `gen_random_uuid()` | Primary Key |
| `user_id` | `UUID` | NO | — | FK -> `users.id` (ON DELETE CASCADE) |
| `page_url` | `TEXT` | NO | — | URL quiz was based on |
| `page_title` | `VARCHAR(500)` | YES | NULL | Title of the page the quiz was based on (denormalized for history display; NULL for legacy rows) |
| `questions_payload`| `JSONB` | NO | — | List of question objects, options, correct index. `total_questions` is derived from this JSONB array length — no dedicated column |
| `user_answers` | `JSONB` | YES | NULL | User's submitted option indices |
| `score` | `INTEGER` | YES | NULL | Points scored (e.g. 4/5) |
| `created_at` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | Quiz generation timestamp |
| `submitted_at` | `TIMESTAMPTZ` | YES | NULL | Grading/submission timestamp; NULL for generated-but-unsubmitted quizzes (`is_submitted: false` in history responses) |

### 2.11 `ai_feedback` (BR-15 — Evaluation & User Feedback)
User ratings and error reports on AI responses.
| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | `UUID` | NO | `gen_random_uuid()` | Primary Key |
| `user_id` | `UUID` | NO | — | FK -> `users.id` (ON DELETE CASCADE) |
| `message_id` | `UUID` | NO | — | FK -> `messages.id` (ON DELETE CASCADE) |
| `rating` | `VARCHAR(10)` | NO | — | `helpful` or `unhelpful` |
| `report_reason` | `VARCHAR(50)` | YES | NULL | `inaccurate`, `hallucination`, `harmful`, `other` |
| `comment` | `TEXT` | YES | NULL | Optional user explanation |
| `created_at` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | Feedback timestamp |
| `updated_at` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | Last updated timestamp |
*(Unique Constraint: `[user_id, message_id]`. Duplicate submissions atomically update the existing record).*

---

### 2.12 `auth_sessions` (Feature A — Session Lifecycle)
One login/OAuth session owns an entire refresh-token chain. It is distinct from tab reading sessions.
| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | `UUID` | NO | `gen_random_uuid()` | Session PK; JWT `sid` claim |
| `user_id` | `UUID` | NO | — | FK -> `users.id` (ON DELETE CASCADE) |
| `device_info` | `VARCHAR(255)` | YES | NULL | Device/browser metadata |
| `expires_at` | `TIMESTAMPTZ` | NO | — | Initial refresh expiry; extended on successful rotation |
| `revoked_at` | `TIMESTAMPTZ` | YES | NULL | NULL while session is active |
| `revocation_reason` | `VARCHAR(20)` | YES | NULL | `logout` or `security`; set together with `revoked_at` |
| `created_at` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | Login/OAuth timestamp |
*(Unique Constraint: `[id, user_id]` for the composite token ownership FK. Revocation reason and timestamp must both be NULL or both non-NULL.)*

All authenticated requests validate session ownership, expiry and revocation in PostgreSQL. Grace-cache lookup is never a replacement for this check. See `.docs/technical/auth-flow.md` for locking, cleanup and temporary refresh failure behavior.

### 2.13 `email_verification_tokens` (Feature A — Mandatory Email Verification)
Single-use hashed tokens sent via Resend to verify a user's email address before login is permitted. The plaintext token exists only inside the emailed link: the database stores exclusively its SHA-256 hex digest. Tokens are generated with 256-bit URL-safe entropy (`secrets.token_urlsafe(32)`).
| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | `UUID` | NO | `gen_random_uuid()` | Primary Key |
| `user_id` | `UUID` | NO | — | FK -> `users.id` (ON DELETE CASCADE) |
| `token_hash` | `VARCHAR(255)` | NO | — | Unique SHA-256 hex digest of the verification token; plaintext never persisted |
| `expires_at` | `TIMESTAMPTZ` | NO | — | Expiration timestamp (`VERIFICATION_TOKEN_TTL_HOURS`, default 24h); expired tokens return `400 VERIFICATION_TOKEN_EXPIRED` |
| `used_at` | `TIMESTAMPTZ` | YES | NULL | Set when the token is consumed; a used token cannot be replayed |
| `created_at` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | Token issuance timestamp |
*(Unique `token_hash`; indexes on `(user_id)` and `(token_hash)`. Verification compares hashes with `secrets.compare_digest`. Stale/expired rows may be purged by a maintenance job; deletion does not affect verified users.)*

### 2.14 `password_reset_tokens` (Feature A — Password Reset)
Single-use hashed tokens sent via Resend to reset a forgotten password. Same hash-at-rest discipline as `email_verification_tokens`: the plaintext token lives only in the email link, the database stores only the SHA-256 hex digest of a 256-bit URL-safe random value.
| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | `UUID` | NO | `gen_random_uuid()` | Primary Key |
| `user_id` | `UUID` | NO | — | FK -> `users.id` (ON DELETE CASCADE) |
| `token_hash` | `VARCHAR(255)` | NO | — | Unique SHA-256 hex digest of the reset token; plaintext never persisted |
| `expires_at` | `TIMESTAMPTZ` | NO | — | Expiration timestamp (`PASSWORD_RESET_TOKEN_TTL_MINUTES`, default 60 minutes); expired tokens return `400 RESET_TOKEN_EXPIRED` |
| `used_at` | `TIMESTAMPTZ` | YES | NULL | Set when the token is consumed; a used token cannot be replayed |
| `created_at` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | Token issuance timestamp |
*(Unique `token_hash`; indexes on `(user_id)` and `(token_hash)`. Successful reset consumes the token, updates the password and revokes every `auth_sessions` row of the user with reason `security` — see `.docs/technical/auth-flow.md` §2.5 and §2.8.)*

### 2.15 `usage_daily` (AI Usage Tracking — BE-20)
Daily per-user/provider/model aggregate counters, upsert-incremented after each completed AI generation. Pure metadata: no message IDs, prompts or response content are recorded, so Privacy Mode remains fully compatible.
| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | `UUID` | NO | `gen_random_uuid()` | Primary Key |
| `user_id` | `UUID` | NO | — | FK -> `users.id` (ON DELETE CASCADE) |
| `date` | `DATE` | NO | — | Aggregation day (UTC) |
| `provider` | `VARCHAR(50)` | NO | — | Provider used (`openai`, `gemini`, `claude`) |
| `model` | `VARCHAR(100)` | NO | — | Model name used |
| `request_count` | `INTEGER` | NO | `0` | Number of completed generations |
| `input_tokens` | `BIGINT` | NO | `0` | Sum of provider-reported input tokens (0 when metadata missing) |
| `output_tokens` | `BIGINT` | NO | `0` | Sum of provider-reported output tokens (0 when metadata missing) |
| `updated_at` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | Last increment timestamp |
*(Unique Constraint: `[user_id, date, provider, model]`. Writes use an atomic upsert-increment (`ON CONFLICT ... DO UPDATE SET request_count = usage_daily.request_count + 1, input_tokens = usage_daily.input_tokens + EXCLUDED.input_tokens, ...`). Streams cancelled mid-flight before the provider's usage frame may be absent from the aggregate; rows are not part of `/sync` — see `.docs/api/endpoints.md` §8.)*

### 2.16 `admin_audit_logs` (Admin Audit Trail — BE-27, planned; migration `0008`)
Append-only behavioral metadata of administrative actions: who changed which account, when, and with what outcome. Content-free — no reading text, no decrypted keys, no emails beyond the recorded UUIDs — so it sits **outside the Privacy Mode storage matrix** (Privacy Mode governs user reading/conversation data, not records of moderation the admin themselves performed).
| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | `UUID` | NO | `gen_random_uuid()` | Primary Key |
| `actor_user_id` | `UUID` | NO | — | FK -> `users.id` (ON DELETE CASCADE); the admin (or CLI service identity) who performed the action |
| `target_user_id` | `UUID` | YES | NULL | FK -> `users.id` (ON DELETE SET NULL); affected account, NULL for CLI-wide actions |
| `action` | `VARCHAR(50)` | NO | — | Enum: `user_status_changed`, `password_reset_link_sent`, `role_promoted_cli`, ... |
| `details` | `JSONB` | NO | `'{}'` | Action payload, e.g. `{"old_status": "active", "new_status": "banned"}` |
| `request_id` | `VARCHAR(64)` | YES | NULL | Correlation ID from the HTTP request; NULL for CLI-written rows |
| `created_at` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | Action timestamp |

*(Indexes: `(actor_user_id, created_at DESC)` for "what did this admin do" history and `(target_user_id)` for "what happened to this account". Append-only in the MVP — no update/delete API; rows are written by `PATCH /admin/users/{id}/status` (§9.3), `POST /admin/users/{id}/send-reset-link` (§9.5, once BE-19 code lands) and directly by the `role_promoted_cli` CLI. **Retention: 90 days** — cleanup job is planned (deferred to a later task); until it exists, expired rows are harmless behavioral metadata. No frontend UI for the MVP; operators query via `psql` or `GET /admin/audit-logs` (endpoints §9.6).)*

## 3. High-Volume Composite Indexes

Synchronized creates/updates, soft deletes, message appends and history clearance allocate `updated_at` under the `users` row lock using the server-only `sync_clock` (ADR-013). Clients cannot set this field. Per-entity cursor indexes include `(user_id, updated_at, id)` without excluding tombstones.
| Index Name | Table | Columns | Purpose |
|---|---|---|---|
| `idx_conversations_user_updated` | `conversations` | `(user_id, is_deleted, updated_at DESC)` | High-speed retrieval of user chat sessions without full-table scans |
| `idx_messages_conversation_created` | `messages` | `(conversation_id, created_at ASC)` | Fast chronological retrieval of messages in a conversation thread |
| `idx_highlights_user_url` | `highlights` | `(user_id, md5(page_url))` B-tree expression | Bounded index entries for valid URLs up to 8,192 characters; lookups also compare the full URL to exclude digest collisions |
| `idx_user_api_keys_active` | `user_api_keys` | `(user_id, provider, is_active)` | Sub-millisecond active BYOK key lookup during AI stream dispatch |
| `idx_reading_history_user_visited`| `reading_history` | `(user_id, visited_at DESC)` | History pagination and recent reading lookups |
| `idx_quiz_records_user_created` | `quiz_records` | `(user_id, created_at DESC)` | Quiz history pagination and UTC date-range filtering (`GET /quiz`, `GET /quiz/stats`) |
| `idx_quiz_records_user_score` | `quiz_records` | `(user_id, score)` | Submitted-quiz aggregates for `GET /quiz/stats` (attempts/avg-score per day and overall) |
| `idx_auth_sessions_user` | `auth_sessions` | `(user_id, revoked_at)` | Session validation and account-wide revocation |
| `idx_refresh_tokens_session` | `refresh_tokens` | `(session_id)` | Chain revocation and cleanup |
| `idx_conversations_sync` | `conversations` | `(user_id, updated_at, id)` | Unified sync including tombstones |
| `idx_highlights_sync` | `highlights` | `(user_id, updated_at, id)` | Unified sync including tombstones |
