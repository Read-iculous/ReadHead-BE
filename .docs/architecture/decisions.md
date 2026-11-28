# Architecture Decision Records (ADRs)

## ADR-001: Backend-Mediated AI Calls with BYOK Model
- **Status**: Accepted
- **Context**: The browser extension could either call AI providers directly with user keys or route through the backend.
- **Decision**: Route all AI calls through the ReadHead backend while having users supply their own API keys (BYOK).
- **Consequences**:
  - *Pros*: Centralized prompt engineering, privacy filters, token usage diagnostics, audit trails, and multi-turn history persistence without bloating the extension.
  - *Cons*: Backend handles streaming traffic and must guarantee robust security (Envelope Encryption at rest, ephemeral in-memory decryption) for stored keys.

---

## ADR-002: Server-Sent Events (SSE) for Real-Time AI Generation
- **Status**: Accepted
- **Context**: AI generation can take 5-20 seconds. Users need instant visual feedback. We evaluated WebSockets vs SSE vs standard HTTP.
- **Decision**: Adopt Server-Sent Events (`text/event-stream`) for AI streaming endpoints.
- **Consequences**:
  - *Pros*: Simple, runs over standard HTTP/HTTPS, natively supported by browser `EventSource` and `fetch` with readable streams, avoids WebSocket connection state management complexity.
  - *Cons*: One-way communication from server to client per request (sufficient for prompt -> stream responses).

---

## ADR-003: Symmetric AES-256-GCM Encryption with Keyring Support
- **Status**: Accepted
- **Context**: The backend needs to decrypt user API keys to make upstream calls on their behalf, so one-way hashing (like bcrypt) cannot be used. Key rotation must not cause downtime, and nonce reuse in GCM mode is catastrophic.
- **Decision**: Store API keys encrypted using **AES-256-GCM** (Authenticated Encryption with Associated Data). Ciphertext is stored as `<version>:<base64_nonce>:<base64_ciphertext>:<base64_auth_tag>` (e.g. `v1:...`, `v2:...`). 
  1. **Strict Nonce Isolation**: Every encryption call MUST generate a cryptographically secure random 12-byte Nonce via `secrets.token_bytes(12)`. Static or predictable nonces are strictly prohibited to prevent GCM Nonce Reuse attacks.
  2. **Rotation order**: Load both versions everywhere, switch all writers to the new version, migrate with ciphertext compare-and-swap, then verify zero old-version rows/writers before removing the old live key. Keep recovery keys for retained backups. Follow `.docs/development/commands.md` for the runbook.
  3. **Keyring Support**: The application supports a Keyring dictionary (`ENCRYPTION_MASTER_KEYS={"v1":"...", "v2":"..."}`) allowing running workers to decrypt both old and new versions concurrently, while new writes always use `CURRENT_KEY_VERSION`. Fernet and CBC modes are explicitly eliminated.
- **Consequences**:
  - *Pros*: Strong cryptographic security at rest with authentication tag verification preventing ciphertext tampering. Dual-key keyring enables 100% zero-downtime key rotation.
  - *Cons*: Keyring rotation requires keeping the old key in configuration until the background migration re-encrypts all database records.

---

## ADR-004: Session-Scoped JWT Rotation and Failure Isolation
- **Status**: Accepted; backend implemented, automated error/concurrency verification deferred.
- **Decision**: Login/OAuth creates `auth_sessions`; access tokens last 15 minutes, refresh tokens 30 days, and both carry the same `sid` throughout a rotation chain. PostgreSQL session expiry/revocation is checked on authenticated requests and before returning any cached pair.
- **Concurrency**: Redis lock `lock:refresh:{sid}:{token_hash}` uses a 5-second owner-checked lease, a post-acquisition cache recheck and a 2-second bounded wait. PostgreSQL session-row locking plus an atomic conditional token update is the final double-rotation guard, including Redis failure/lease expiry.
- **Grace**: `refresh_grace:{sid}:{old_token_hash}` lasts 30 seconds and is indexed by `refresh_grace_keys:{sid}`. Logout revokes the whole session and its tokens, then cleans that session's exact cache keys. Cached pairs from a revoked session are unusable even if cleanup fails.
- **Failure isolation**: Track token reasons `rotated`, `logout`, `security` and `revoked_at`. A missing rotation result within the grace interval returns `503 REFRESH_TEMPORARILY_UNAVAILABLE`; an older rotated token returns `401 REFRESH_TOKEN_REVOKED`. Neither cache failure nor lock contention alone revokes unrelated sessions. Explicit security events revoke affected sessions. Do not persist token-pair recovery copies in PostgreSQL in the MVP.
- **Canonical protocol**: `.docs/technical/auth-flow.md` §2.3–2.5 specifies validation, temporary failures, refresh-only retries and cleanup.

---

## ADR-005: Hybrid Client/Server Storage Strategy
- **Status**: Accepted
- **Context**: Chrome extensions have access to `chrome.storage.local`, while cross-device sync requires cloud storage.
- **Decision**: Store durable entities (User profile, encrypted API keys, chat history, highlights, privacy preferences) in PostgreSQL. Store volatile tab state, active DOM extract cache, and in-flight draft text locally in the browser extension.
- **Consequences**:
  - *Pros*: Minimal database bloat from transient page browsing; seamless synchronization for user value data across different browsers/machines.

---

## ADR-006: Pre-flight Sensitive Content Inspection (Feature H)
- **Status**: Accepted
- **Context**: BRS and SRS require that sensitive content (credentials, PII, financial data) must not be transmitted to external AI providers without user consent.
- **Decision**: Implement a pre-flight privacy check that scans **100% of the outbound text payload** (`selected_text`, `page_content`, `user_prompt`) against high-speed regex and heuristic patterns (< 5ms). By default, transmission is blocked with a 400 `SENSITIVE_DATA_DETECTED` response containing redacted excerpts. Users can review and explicitly override with `bypass_protection: true`.
- **Consequences**:
  - *Pros*: Zero uninspected data transmitted to external LLMs; strict compliance with privacy mandates.
  - *Cons*: Regex rules must be maintained and tuned to avoid excessive false positives.

---

## ADR-007: Optimistic Concurrency Control for Multi-Device Sync (Feature J)
- **Status**: Accepted
- **Context**: Users can read on multiple machines (e.g. laptop and desktop). Concurrent edits to conversations or settings could cause silent data loss if "last-write-wins" or race-prone `SELECT...UPDATE` is used naively.
- **Decision**: Introduce integer `version` columns on synchronized records. Sync mutations execute an **Atomic Conditional SQL Update**:
  ```sql
  UPDATE conversations 
  SET title = :title, version = version + 1, updated_at = :sync_timestamp
  WHERE id = :id AND version = :base_version
  RETURNING id;
  ```
  Allocate `:sync_timestamp` under the user-row lock according to ADR-013; filter by authenticated `user_id` in the real query.
  If affected rows == 0, the server immediately raises a `409 SYNC_CONFLICT` error with both versions, strictly preventing silent data loss without requiring table-level locks.
- **Consequences**:
  - *Pros*: Strictly complies with `FR-SYN-05` ("System SHALL NOT silently overwrite preserved data") and eliminates multi-thread race conditions.
  - *Cons*: Requires client UI to prompt the user or apply deterministic merge rules when conflicts arise.

---

## ADR-008: Source Grounding and Uncertainty Attribution (Feature E, BR-12~14)
- **Status**: Accepted
- **Context**: When answering reading questions, AI models may hallucinate facts not present in the article. BRS explicitly mandates that source grounding be prioritized and non-grounded external knowledge be identified.
- **Decision**: Include grounding attributes in AI response payloads and message models: `is_grounded` (boolean), `grounding_notes` (string), and `uncertainty_flag` (boolean). System prompts instruct the LLM to explicitly state when an answer is based on external training data rather than the user's active page.
- **Consequences**:
  - *Pros*: Enhances trust and transparency; conforms to ISO requirements for verifiable AI.
  - *Cons*: Requires careful prompt engineering and post-processing.

---

## ADR-009: Strict Prohibition of Silent Automated AI Retries (FR-AI-10, FR-ERR-04, FR-KEY-06)
- **Status**: Accepted
- **Context**: When a network drop, provider quota limit, or key error occurs, naively auto-retrying failed AI requests could drain user quota or send unintended requests once connection resumes.
- **Decision**: The backend and extension shall **never** automatically resubmit failed or pending AI requests. Unsent prompts are preserved in local storage drafts, and the user must manually trigger the retry.
- **Consequences**:
  - *Pros*: Protects user from unexpected LLM billing, duplicate actions, and privacy violations.
  - *Cons*: Requires user to click "Retry" after fixing connection or keys.

---

## ADR-010: Real-Time Session Invalidation, Redis Downtime & Degraded Mode
- **Status**: Accepted
- **Context**: Access Tokens have a 15-minute lifetime. When an admin bans an account or a user deletes their profile, waiting for JWT expiration creates a security risk. Conversely, if Redis experiences downtime, hard-failing readiness probes (503) causes Kubernetes/Ingress to kill routing, preventing built-in database fallbacks from executing.
- **Decision**:
  1. **New Requests & Token Revocation**: Store immediate revocation markers in Redis key `revoked_users:{user_id}` with TTL = 3600 seconds whenever an account is suspended, banned, or deleted. The `get_current_user` dependency checks Redis markers plus authoritative PostgreSQL user/session validity. Suspended users return `401 USER_SUSPENDED`; revoked access-token sessions return `401 UNAUTHORIZED`.
  2. **Active Streams**: Running SSE async generators inspect user and session revocation markers between yielded tokens. User suspension/deletion emits `event: error` (`USER_SUSPENDED`); session logout emits `UNAUTHORIZED`. The stream then terminates. Redis outage follows the degraded-mode exception below.
  3. **Readiness Probe & Degraded Mode Policy**:
     - PostgreSQL is a **hard dependency**: if DB is unreachable, `/api/v1/health` returns `503 Service Unavailable`.
     - Redis is a **soft dependency with graceful degradation**: if Redis is unreachable while DB is healthy, `/api/v1/health` returns `200 OK` with status `"degraded"` (`{"status": "degraded", "checks": {"database": {"status": "healthy"}, "redis": {"status": "unhealthy"}}}`). This keeps pods in rotation while degrading non-critical features:
       - *Auth*: Checks user/session revocation directly against PostgreSQL. Refresh uses the same DB session-row lock and conditional update; unavailable rotation results return `503 REFRESH_TEMPORARILY_UNAVAILABLE` without global logout (ADR-004).
       - *Rate Limiting*: Falls back to local in-memory sliding window or permits requests.
       - *Streaming Concurrency*: Bypasses multi-stream restriction temporarily; active streams ignore Redis connection loss mid-stream and continue delivering tokens to completion.
       - *Ephemeral Quizzes*: Returns `503 SERVICE_DEGRADED` as quizzes in Privacy Mode require caching.
- **Consequences**:
  - *Pros*: Instantaneous session revocation in normal operation, while eliminating system-wide outages from transient Redis restarts.

---

## ADR-011: SSE Concurrency Limits, Client-Side PDF Parsing & Untrusted Context Fencing
- **Status**: Accepted
- **Context**: Unbounded long-lived SSE connections can exhaust backend workers. PDF document uploads can balloon server disk/RAM. Untrusted web page text can harbor prompt injection attacks against LLMs.
- **Decision**:
  1. **SSE Concurrency**: Enforce a maximum of **2 active concurrent SSE streams** per user (`active_streams:{user_id}` in Redis); excess streams reject with `429 STREAM_CONCURRENCY_EXCEEDED`. Rate limits (native async Redis fixed windows) apply strictly to the initial HTTP handshake.
  2. **Zero-Binary PDF Handling**: Browser extension extracts clean text locally using bundled Mozilla `pdf.js` (max 102,400 bytes UTF-8 text extract); zero raw PDF binaries are uploaded to the backend.
  3. **Prompt Injection Fencing**: Backend wraps web-derived contexts in XML delimiter tags (`<untrusted_web_context>` and `<user_selected_text>`) with immutable system prompt instructions commanding the LLM to treat inner text purely as passive reference data.
- **Consequences**:
  - *Pros*: Protects server capacity, honors zero-document retention privacy, and hardens LLM against adversarial page injections.
  - *Cons*: Extension must bundle `pdf.js` worker and enforce 100 KB text truncation.

---

## ADR-012: Reading Session Identification, Tab Bind Flow & Ephemeral Privacy Mode Contract
- **Status**: Accepted
- **Context**: Relying purely on `page_url` fails tab isolation when multiple tabs open the same URL or when reading history is cleared (`page_url = NULL`). Privacy Mode multi-turn chat lacked an explicit history transport contract and bind flow.
- **Decision**:
  1. **Session Identification & Explicit Bind Flow**:
     - Browser tabs generate a `reading_session_id` (UUIDv4) stored in tab `sessionStorage`.
     - When opened from the dashboard or history list, `conversations.reading_session_id` defaults to `NULL` (unbound readonly mode).
     - Continuing an existing standard-mode conversation requires non-null matching stored/requested session IDs. An unbound conversation remains read-only even when the request also omits its session ID (`400 TAB_CONTEXT_MISMATCH`).
     - To interact with an existing conversation from an active tab, the client sends `POST /api/v1/ai/conversations/{id}/bind` passing its `reading_session_id`.
     - If the conversation is currently streaming tokens in another tab, the bind request is rejected with `409 CONVERSATION_BUSY`.
     - When history is cleared (`page_url IS NULL`), any tab can bind to the conversation and context checking against the original URL is bypassed.
  2. **Privacy Mode Multi-turn Chat Contract**:
     - In Privacy Mode (`privacy_mode_enabled: true`), zero conversation or message rows are written to PostgreSQL.
     - The client maintains message history in tab memory (`sessionStorage`) and transmits previous turns via the optional `ephemeral_history` field in `POST /api/v1/ai/stream`.
     - `ephemeral_history` is capped at a sliding window of max 10 messages (max 16KB UTF-8 payload), restricted to roles `user` and `assistant`.
     - The backend applies standard PII inspection to `ephemeral_history` before passing it to LLM context, and purges all instances from memory once the stream terminates.
  3. **Ephemeral Quiz**: Quizzes generated in Privacy Mode are stored in Redis (`ephemeral_quiz:{quiz_id}`) with a 30-minute TTL for interactive submission and grading, completely bypassing the persistent `quiz_records` database table.
- **Consequences**:
  - *Pros*: Robust tab isolation, safe multi-turn conversations in zero-retention mode, and clear ownership transfers across tabs.

---

## ADR-013: One Unified Sync Cursor and Non-Destructive Full Resync
- **Status**: Accepted; backend implemented, automated error/concurrency verification deferred.
- **Decision — one cursor**: Merge user-owned `conversations`, `highlights` and `user_settings` rows (including tombstones) with `UNION ALL`, label their `entity_type` as `conversation`, `highlight`, `settings`, and order by `(updated_at ASC, entity_type ASC, id ASC)`. `limit` (1–100) applies to the combined result, not to each table. Messages are fetched separately. Only `cursor`/`next_cursor` exist; there are no per-entity cursor fields.
- **Opaque cursor format**: Base64url JSON with `v: 1`, `kind`, `t` and `anchor`. A `position` cursor additionally contains `entity_type` and a full UUID `id`; it resumes strictly after that tuple. A `checkpoint` cursor resumes at `updated_at > t`. `anchor` is the time of the previous completed checkpoint, or the initial full-pull start time, and stays unchanged throughout pagination. Validate fields/types and reject unsupported/malformed cursors with `400 INVALID_SYNC_CURSOR`; queries always filter by the authenticated user.
- **Concurrent writes and commit order**: All synchronized writes (including direct REST operations, user settings creation, message appends, history clearance, soft deletes and sync push) first lock the owning `users` row using `SELECT ... FOR UPDATE` in a short transaction. Allocate a timestamp `GREATEST(clock_timestamp(), users.sync_clock + INTERVAL '1 microsecond')`, update `users.sync_clock`, and stamp changed synchronized rows with that value. Preserve the existing conditional `version` update. Acquire the user lock before entity locks and hold it through commit. Never stamp these writes solely with transaction-start `NOW()`.
- **Pull algorithm**: Each page obtains the same user row lock before reading the merged result. Fetch `limit + 1` rows to compute `has_more`; return at most `limit`, grouped into the documented response arrays/object. If more rows exist, `next_cursor` is a `position` at the last returned tuple, retaining `anchor`. Otherwise advance `users.sync_clock` with the allocator and return a `checkpoint` whose `t` and `anchor` equal that allocated value, even for an empty page. Commit and release the lock before returning. Thus a later writer must receive a timestamp after the completed checkpoint, including after a slow transaction or clock rollback. A row changed again between pages may be delivered again at a higher version; the client upserts by ID/version. This synchronizes latest state, not an audit log of every intermediate edit.
- **Retention**: Retain tombstones at least 30 days from their deletion/update timestamp. The purge job takes the same user lock. Reject a cursor if `anchor` is older than 30 days with `410 CURSOR_EXPIRED` and `requires_full_sync: true`. A full pull (`cursor: null`) includes current live rows; expired clients must rebuild their synced cache. Initial pagination uses the full-pull start as `anchor`, so old live rows do not themselves cause expiration.
- **Non-destructive resync**: Preserve credentials, drafts, ephemeral tab state and pending mutations. Build a new user-scoped synced cache in staging storage from `cursor: null`, then atomically replace only the old synced cache and install the completed checkpoint after every page succeeds. On failure retain the previous cache, cursor and pending work. New edits during the rebuild remain queued separately. Reconcile pending mutations against fresh server versions; stale edits/deletes surface conflicts and require resolution, never silent overwrite or resurrection. Do not replay queued AI requests. Account logout/switch still follows the separate account-isolation purge rule.
- **Scope**: `users.sync_clock` is server-only metadata and is not part of user profile/settings mutation payloads. No long-lived DB snapshot/connection is held across HTTP pages.

---

## ADR-014: Database Session Lifecycle Decoupling & Post-Stream Write Order
- **Status**: Accepted
- **Context**: SSE streams can take 15–45 seconds. Holding database connections across streaming exhausts pools. Furthermore, if `event: done` is dispatched to the client before the database transaction commits the assistant message, a database commit failure would cause the client to display success while the message is permanently lost on page reload.
- **Decision**: Decouple the database session lifecycle into strictly ordered phases:
  1. **Phase 1 (Pre-stream DB Transaction)**:
     - Check out transient DB session.
     - Authenticate user, decrypt BYOK key, verify tab session ownership.
     - If standard mode: Create conversation (if new) and insert `user message` into `messages` table. Allocate the sync timestamp and increment the conversation version for this append under the ADR-013 user-row lock; commit and close the DB session.
  2. **Phase 2 (Streaming Loop - Zero DB Connection)**:
     - Stream LLM tokens via SSE (`event: start`, `event: token`, `event: citation`).
     - Inspect Redis cancellation flags without DB connection.
  3. **Phase 3 (Post-stream DB Commit BEFORE Event Done)**:
     - Stream generation finishes from LLM.
     - Check out fresh transient DB session.
     - Insert `assistant message`, increment `conversation.version = version + 1`, update `conversation.updated_at` using the ADR-013 sync timestamp allocator.
     - Commit DB transaction.
     - **Only after DB commit successfully finishes**, dispatch `event: done` to client.
     - **Failure Handling**: If the database commit fails, do NOT send `event: done`. Instead, dispatch `event: error` with code `PERSISTENCE_FAILED`. For the MVP, the client keeps the reply in the current UI memory, labels it "Not saved", and allows copying. No retry-save endpoint or automatic AI replay exists. In Privacy Mode, do not persist this UI text outside the declared ephemeral storage.
  4. **Privacy Mode**: Skip DB writes in Phase 1 and Phase 3 entirely; dispatch `event: done` immediately after LLM finishes streaming.
- **Consequences**:
  - *Pros*: Zero pool starvation, guaranteed message persistence before client receives success signal, clear error handling on storage failures.

---

## ADR-015: Mandatory Email Verification via Resend, Hashed Tokens & Reset-Driven Revocation
- **Status**: Accepted (docs complete; NOT implemented — BE-19)
- **Context**: Password accounts could previously log in immediately after registration, leaving unverified/throwaway email addresses in the user base. Password recovery did not exist, and admins had no way to help users regain access. Transactional email requires a deliverable sending domain and abuse-resistant token handling.
- **Decision**:
  1. **Provider**: Send all transactional email (verification, reset, provider-link notifications) through **Resend** via its HTTPS REST API using direct `httpx` calls — matching the project's existing direct-httpx pattern for simple JSON integrations; no dedicated SDK. Configure SPF/DKIM/DMARC for the sending domain.
  2. **Mandatory verification**: Password registration creates the account with `is_verified = FALSE`, dispatches the verification email fire-and-forget (3 retries with exponential backoff; mail failure NEVER fails registration), and login stays blocked with `403 EMAIL_NOT_VERIFIED` (broadened: password login AND unverified-provider OAuth) until the emailed token is consumed. OAuth (Google/GitHub) accounts are verified by their provider.
  3. **Tokens hashed-at-rest**: Verification/reset tokens are 256-bit URL-safe CSPRNG values; the database stores only their SHA-256 hex digests (`email_verification_tokens` / `password_reset_tokens`, migration `0004`). Plaintext tokens exist solely inside email links. Single-use (`used_at`), TTL-bounded (24h verification / 60-minute reset), constant-time comparison.
  4. **Revoke-all-on-reset**: A successful password reset consumes the token and revokes EVERY `auth_sessions` row of the user with reason `security`, reusing the ADR-004/auth-flow §2.5 revocation mechanism; all devices must sign in again.
  5. **Anti-abuse**: Neutral always-200 forgot/resend responses with stable timing (anti-enumeration), 3/hour per-email resend cap plus the shared auth bucket (email bombing), uniform 401 login failures (credential stuffing), and no token/mail-payload logging (`FR-OPS-03`).
- **Consequences**:
  - *Pros*: Verified email as an account-recovery and trust anchor; database leaks yield no usable links; stolen sessions die on password reset; deliverability managed by Resend.
  - *Cons*: Users must reach their inbox before first login; Resend becomes a soft external dependency (failures degrade to `verification_email_sent: false`, never block registration); DNS records must be maintained.

---

## ADR-016: Backend-Mediated Usage Tracking via Daily Aggregates (Privacy-Compatible)
- **Status**: Accepted (docs complete; NOT implemented — BE-20)
- **Context**: Users need visibility into their AI consumption, but per-message usage records would create a content-linked telemetry trail — unacceptable for Privacy Mode — and admin per-user usage views would violate the project's privacy guardrails.
- **Decision**:
  1. **Aggregate-only storage**: After each completed generation, upsert-increment one row per `(user_id, date, provider, model)` in `usage_daily` (migration `0005`): `request_count`, `input_tokens`, `output_tokens`. No message IDs, URLs, prompts or response text are recorded, so the aggregate carries zero content linkage.
  2. **Provider metadata**: Parse the terminal frame of each provider — OpenAI (requires `stream_options.include_usage`), Anthropic (`message_delta`), Gemini (`usageMetadata`). Missing metadata stays `null` in the done event (`total_tokens` remains nullable as today; `input_tokens`/`output_tokens` are added) and stores zeros in the aggregate — never fabricated.
  3. **Privacy Mode compatibility**: Private-mode generations still increment usage (pure counters, no content rows), unlike conversation/message writes which are skipped entirely.
  4. **Access**: `GET /users/me/usage?period=day|month&from=&to=` serves the authenticated owner only. Admins see NO per-user usage in the MVP — admin telemetry remains aggregate and content-free. `usage_daily` and api-keys are out of `/sync` scope.
- **Consequences**:
  - *Pros*: User-facing consumption transparency with a single bounded table; Privacy Mode contract intact; minimal admin privacy surface.
  - *Cons*: Streams cancelled before the terminal frame are under-counted (accepted and documented); per-request (sub-daily, per-message) analytics are impossible retroactively.

---

## ADR-017: Personalization Consent & Proactive Dedup (docs complete; NOT implemented — BE-23)
- **Status**: Accepted (docs complete; NOT implemented)
- **Context**: Personalizing assistance (adapting explanation level/detail to reading proficiency, improving proactive suggestions) requires using `reading_history` and AI interactions. Privacy Mode only stops *new* history writes and does not express consent to *use* existing data for personalization. Separately, ISSUE-043 showed `POST /ai/proactive-suggest` calling the LLM on every eligible dwell event, so a retry loop can burn user quota.
- **Decision**:
  1. **Consent column**: `user_settings.personalization_consent BOOLEAN NOT NULL DEFAULT FALSE` (migration `0006`). Opt-in only; default off. **Independent of `privacy_mode_enabled`** — neither flag implies or toggles the other. Revocation sets the flag to `FALSE` and does NOT delete previously stored data (the client prompts the user about existing data). The flag is part of the synchronized `settings` entity, so revocation propagates to all devices, and takes effect immediately.
  2. **Enforcement rule**: Every current and future code path that uses `reading_history` or AI interactions for personalization MUST re-read `personalization_consent` under the same `users` row lock used by settings updates (the ISSUE-015 stale-snapshot pattern) and skip personalization when it is `FALSE`. Admins see no personalization data or consent-derived views.
  3. **Purpose bound**: Consent covers exactly: (a) adapting explanation level / answer detail to the user's reading proficiency, and (b) improving proactive suggestions. Any new purpose requires revisiting this ADR.
  4. **Proactive dedup**: A Redis-only TTL cache keyed `(user_id, paragraph_hash)` (SHA-256 of the normalized paragraph) with TTL 300 seconds (5 minutes). A cache hit returns `{has_suggestion: false}` without any LLM call; the key is written only after a successfully generated suggestion. The cache is never persisted to PostgreSQL, is not part of `/sync`, and degrades silently (dedup skipped) during Redis outages. This closes ISSUE-043 (resolved-in-docs).
- **Consequences**:
  - *Pros*: Explicit, auditable consent basis for personalization; users keep their data when revoking; quota-abuse loops cannot multiply proactive LLM calls; zero schema cost for the dedup cache.
  - *Cons*: A 5-minute window means the same paragraph can trigger one repeated suggestion per window (accepted); consent re-reads add a lock read to personalization paths.

---

## ADR-018: Comprehension Insights — Rule-Based, On-The-Fly Aggregates (docs complete; NOT implemented — BE-24)
- **Status**: Accepted (docs complete; NOT implemented)
- **Context**: The product wants a second-tier "Comprehension Insight" (Tầng 2) that tells users which domains they struggle with and lets proactive assistance adapt accordingly. A dedicated insight table or an ML pipeline would add schema, retention and privacy costs disproportionate to an MVP, and `messages` lacks a `task` column to attribute assistance requests precisely.
- **Decision**:
  1. **On-the-fly aggregation, no new tables, no ML**: Insights are computed per `(user, domain)` at request time from `quiz_records` (quiz scores/trend) and `messages`⋈`conversations` (user-turn assistance frequency). `reading_history` dwell time is only a secondary corroborating signal — it never raises the difficulty signal alone (false-positive guard). Deleting the underlying data resets signals automatically because nothing is cached or materialized.
  2. **Access**: `GET /users/me/reading-insights?from&to` (endpoints §3.8) returns per-domain `{avg_quiz_score, quiz_trend, assist_request_rate, difficulty_signal, sample_size, has_sufficient_data}`. All thresholds (quiz windows, 0.6 decay floor, normalized turn ratios, `has_sufficient_data` minima of 2 submitted quizzes / 3 user turns) are configuration constants/env values, not hard-coded logic. Rate bucket: general API bucket.
  3. **Consent gate (ADR-017 boundary)**: *Viewing* one's own insight requires NO consent (it is the user's own data). *Using* the insight to modulate AI behavior — the optional `insight` field on `POST /ai/proactive-suggest` (§5.3) — requires `personalization_consent == true`, re-read under the user row lock at the point of use (ADR-017 enforcement rule).
  4. **Anti-spam (layer 3)**: Insight-driven proactive enrichment is capped at **2 per day per domain** via a Redis counter with a 24h TTL; a dismissal of this suggestion type caches a 24h suppression for that `(user, domain)`. Both are Redis-only (degraded mode skips them), never persisted, and never part of `/sync`. When the cap is reached the ordinary hint still works under the existing 5-minute dedup cache.
  5. **Privacy Mode**: While enabled, no new signals are written; aggregates read only previously stored rows.
- **Limitations (explicit)**:
  - `messages` lacks a `task` column, so `assist_request_rate` proxies assistance requests with **user-turn counts** per domain. Adding a `task` column is deferred to a future migration (would then require re-baselining the normalization).
  - Dwell/reading time is not normalized by word count, so raw dwell is deliberately restricted to a weak secondary signal pending the BC-08 KPI work.
- **Consequences**:
  - *Pros*: Zero schema cost (no new table, migration `0007` only drops the unused bookmark column); deterministic and auditable rules; instant reset on data deletion; consent/privacy boundaries reuse ADR-017 mechanisms unchanged.
  - *Cons*: Rule-based signals are coarser than ML models and cannot retro-analyze before data existed; user-turn proxy over-counts multi-turn chats per domain; thresholds need tuning via configuration as real usage lands.
