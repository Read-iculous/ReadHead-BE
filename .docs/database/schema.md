# Database Schema Specification

## 1. Schema Conventions
- All table names are in `snake_case` plural (e.g. `users`, `api_keys`).
- All primary keys are `UUID` (`gen_random_uuid()`) for security and non-enumerable IDs.
- All timestamps use `TIMESTAMP WITH TIME ZONE` and default to `CURRENT_TIMESTAMP`.
- Optimistic locking columns (`version INTEGER NOT NULL DEFAULT 1`) are added to entities synchronized across devices.
- Soft delete (`is_deleted BOOLEAN NOT NULL DEFAULT FALSE`) is supported on historical user entities.

---

## 2. Table Definitions

### 2.1 `users` (Feature A)
Core user account registry.
| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | `UUID` | NO | `gen_random_uuid()` | Primary Key |
| `email` | `VARCHAR(255)` | NO | — | Unique user email address |
| `hashed_password` | `VARCHAR(255)` | YES | NULL | Salted bcrypt hash (NULL for OAuth-only users) |
| `full_name` | `VARCHAR(150)` | YES | NULL | Display name |
| `avatar_url` | `TEXT` | YES | NULL | Profile image URL |
| `is_active` | `BOOLEAN` | NO | `TRUE` | Whether account is active |
| `is_verified` | `BOOLEAN` | NO | `FALSE` | Email verification status |
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
Tracks active sessions and refresh tokens for revocation and device tracking.
| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | `UUID` | NO | `gen_random_uuid()` | Primary Key |
| `user_id` | `UUID` | NO | — | FK -> `users.id` (ON DELETE CASCADE) |
| `token_hash` | `VARCHAR(255)` | NO | — | SHA-256 hash of refresh token |
| `device_info` | `VARCHAR(255)` | YES | NULL | Browser/OS user agent identifier |
| `expires_at` | `TIMESTAMPTZ` | NO | — | Expiration timestamp |
| `is_revoked` | `BOOLEAN` | NO | `FALSE` | Revocation status |
| `created_at` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | Issued timestamp |

### 2.4 `user_api_keys` (Feature C — BYOK Vault)
User-provided LLM provider API keys encrypted at rest via AES-256.
| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | `UUID` | NO | `gen_random_uuid()` | Primary Key |
| `user_id` | `UUID` | NO | — | FK -> `users.id` (ON DELETE CASCADE) |
| `provider` | `VARCHAR(50)` | NO | — | `openai`, `gemini`, `claude` |
| `encrypted_key` | `TEXT` | NO | — | Symmetrically encrypted API key (AES-256-GCM) |
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
| `target_language` | `VARCHAR(10)` | NO | `'vi'` | Preferred translation language |
| `explanation_level` | `VARCHAR(20)` | NO | `'standard'` | `simple`, `standard`, `expert` |
| `accessibility_profile` | `JSONB` | NO | `'{"dyslexia_font": false, "font_size_delta": 0, "line_spacing": 1.5, "bionic_reading": false, "high_contrast": false}'` | Accessibility & page styling preferences (BG-06, BR-11) |
| `proactive_assistance_enabled`| `BOOLEAN` | NO | `TRUE` | Whether to suggest tips on reading slowdowns (Feature G) |
| `proactive_sensitivity` | `VARCHAR(20)` | NO | `'medium'` | `low`, `medium`, `high` |
| `data_protection_mode` | `BOOLEAN` | NO | `TRUE` | Feature H: Block sensitive PII/secrets outbound by default |
| `privacy_mode_enabled` | `BOOLEAN` | NO | `FALSE` | Global toggle to prevent reading history logs |
| `blacklisted_domains` | `JSONB` | NO | `'[]'` | List of domain patterns to ignore |
| `version` | `INTEGER` | NO | `1` | Optimistic lock version for multi-device sync (Feature J) |
| `updated_at` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | Last settings update |

### 2.6 `conversations` (Feature I & D)
Chat sessions tied to specific reading contexts. Tab-isolated.
| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | `UUID` | NO | `gen_random_uuid()` | Primary Key |
| `user_id` | `UUID` | NO | — | FK -> `users.id` (ON DELETE CASCADE) |
| `title` | `VARCHAR(255)` | NO | `'New Conversation'` | Title / summary of conversation |
| `page_url` | `TEXT` | YES | NULL | Web page URL where conversation started |
| `page_title` | `VARCHAR(500)` | YES | NULL | Document / page title |
| `version` | `INTEGER` | NO | `1` | Sync version (Feature J) |
| `is_deleted` | `BOOLEAN` | NO | `FALSE` | Soft delete flag |
| `created_at` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | Session start |
| `updated_at` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | Last message timestamp |

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
| `is_bookmarked` | `BOOLEAN` | NO | `FALSE` | Quick bookmark flag |
| `visited_at` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | Visit timestamp |
*(Index on `[user_id, visited_at DESC]`)*

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

### 2.10 `quiz_records` (Feature F — Comprehension Questions)
Stores generated quizzes, user responses, and score history.
| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | `UUID` | NO | `gen_random_uuid()` | Primary Key |
| `user_id` | `UUID` | NO | — | FK -> `users.id` (ON DELETE CASCADE) |
| `page_url` | `TEXT` | NO | — | URL quiz was based on |
| `questions_payload`| `JSONB` | NO | — | List of question objects, options, correct index |
| `user_answers` | `JSONB` | YES | NULL | User's submitted option indices |
| `score` | `INTEGER` | YES | NULL | Points scored (e.g. 4/5) |
| `created_at` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | Quiz generation timestamp |

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
