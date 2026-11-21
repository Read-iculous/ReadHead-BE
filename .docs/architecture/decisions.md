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
  2. **Keyring Support**: The application supports a Keyring dictionary (`ENCRYPTION_MASTER_KEYS={"v1":"...", "v2":"..."}`) allowing running workers to decrypt both old and new versions concurrently, while new writes always use `CURRENT_KEY_VERSION`. Fernet and CBC modes are explicitly eliminated.
- **Consequences**:
  - *Pros*: Strong cryptographic security at rest with authentication tag verification preventing ciphertext tampering. Dual-key keyring enables 100% zero-downtime key rotation.
  - *Cons*: Keyring rotation requires keeping the old key in configuration until the background migration re-encrypts all database records.

---

## ADR-004: Dual JWT Token Architecture (Access + Refresh Tokens)
- **Status**: Accepted
- **Context**: Extension users expect long-lived sessions without having to re-authenticate daily, while security requires short-lived access tokens.
- **Decision**: Issue short-lived Access Tokens (60 minutes) and longer-lived Refresh Tokens (30 days) with token rotation on refresh and a 30-second concurrency grace period. Database-backed token tracking allows immediate session revocation.
- **Consequences**:
  - *Pros*: Robust security profile; compromised access tokens expire rapidly; refresh tokens are rotated and can be invalidated upon logout or suspicious activity.
  - *Cons*: Extension needs token-refresh interceptors to handle 401s seamlessly.

---

## ADR-005: Hybrid Client/Server Storage Strategy
- **Status**: Accepted
- **Context**: Chrome extensions have access to `chrome.storage.local`, while cross-device sync requires cloud storage.
- **Decision**: Store durable entities (User profile, encrypted API keys, chat history, highlights, bookmarks, privacy preferences) in PostgreSQL. Store volatile tab state, active DOM extract cache, and in-flight draft text locally in the browser extension.
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
  SET title = :title, version = version + 1, updated_at = NOW() 
  WHERE id = :id AND version = :base_version
  RETURNING id;
  ```
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

## ADR-010: Real-Time Session Invalidation & Token Revocation via Redis
- **Status**: Accepted
- **Context**: Access Tokens have a 60-minute lifetime. When an admin bans an account or a user performs account deletion, waiting up to 60 minutes for JWT expiration creates an unauthorized access vulnerability. Active in-flight AI streams must also be aborted.
- **Decision**:
  1. **New Requests**: Store immediate revocation markers in Redis key `revoked_users:{user_id}` with TTL = 3600 seconds whenever an account is suspended, banned, or deleted. The `get_current_user` auth dependency performs a sub-millisecond Redis check on every authenticated request and rejects revoked users immediately with `401 USER_SUSPENDED` or `401 UNAUTHORIZED`.
  2. **Active Streams**: Running SSE async generators inspect user revocation status between yielded tokens. Upon detecting a revocation event, the generator immediately yields an `event: error` (`USER_SUSPENDED`) and closes the connection.
  3. **Reactivation**: When an admin reactivates an account, the backend updates PostgreSQL `users.status = 'active'` and deletes `revoked_users:{user_id}` from Redis.
  4. **Fail-Safe High Availability**: If Redis experiences transient downtime or connection errors, the `get_current_user` dependency catches `RedisError` and gracefully falls back to checking `users.status` directly against PostgreSQL, guaranteeing zero downtime or 500 error cascades.
- **Consequences**:
  - *Pros*: Instantaneous cross-device session termination for new requests and active streams upon administrative action or account deletion.
  - *Cons*: Adds sub-millisecond Redis check to request pipeline and generator loop.

---

## ADR-011: SSE Concurrency Limits, Client-Side PDF Parsing & Untrusted Context Fencing
- **Status**: Accepted
- **Context**: Unbounded long-lived SSE connections can exhaust backend workers. PDF document uploads can balloon server disk/RAM. Untrusted web page text can harbor prompt injection attacks against LLMs.
- **Decision**:
  1. **SSE Concurrency**: Enforce a maximum of **2 active concurrent SSE streams** per user (`active_streams:{user_id}` in Redis); excess streams reject with `429 STREAM_CONCURRENCY_EXCEEDED`. Rate limits (`slowapi`) apply strictly to the initial HTTP handshake.
  2. **Zero-Binary PDF Handling**: Browser extension extracts clean text locally using bundled Mozilla `pdf.js` (max 100 KB text extract); zero raw PDF binaries are uploaded to the backend.
  3. **Prompt Injection Fencing**: Backend wraps web-derived contexts in XML delimiter tags (`<untrusted_web_context>` and `<user_selected_text>`) with immutable system prompt instructions commanding the LLM to treat inner text purely as passive reference data.
- **Consequences**:
  - *Pros*: Protects server capacity, honors zero-document retention privacy, and hardens LLM against adversarial page injections.
  - *Cons*: Extension must bundle `pdf.js` worker and enforce 100 KB text truncation.

---

## ADR-012: Reading Session Identification & Ephemeral Privacy Mode Mechanics
- **Status**: Accepted
- **Context**: Relying purely on `page_url` fails tab isolation when multiple tabs open the same URL or when Privacy Mode sets `page_url = NULL`. Privacy Mode persistence exceptions (e.g. quiz evaluation, stream interruption) were underspecified.
- **Decision**:
  1. **Session Identification**: The browser extension assigns a unique `reading_session_id` (UUIDv4) stored in tab memory (`sessionStorage`) for each reading tab. Binds with backend `conversations.reading_session_id`. `TAB_CONTEXT_MISMATCH` is returned if an active conversation is hijacked by another tab without an explicit bind.
  2. **Ephemeral Chat**: In Privacy Mode, chat messages are retained strictly in client memory (RAM/sessionStorage) and discarded when the tab closes. Zero rows are written to `conversations` or `messages` in PostgreSQL, even upon SSE stream disconnection.
  3. **Ephemeral Quiz**: Quizzes generated in Privacy Mode are stored in Redis (`ephemeral_quiz:{quiz_id}`) with a 30-minute TTL for interactive submission and grading, completely bypassing the persistent `quiz_records` database table.
- **Consequences**:
  - *Pros*: Guarantees rock-solid tab isolation and true zero-storage privacy compliance while preserving interactive quiz capability.

---

## ADR-013: Composite Cursor Pagination for Multi-Device Synchronization
- **Status**: Accepted
- **Context**: Slicing incremental sync updates purely by timestamp (`updated_at > cursor`) causes skipped records when multiple rows share the same millisecond timestamp and exceed `limit`.
- **Decision**: Standardize `POST /api/v1/sync/pull` on a **Composite Cursor** combining timestamp and unique primary key: `(updated_at, id)`. The cursor is passed as a Base64-encoded JSON string `{"t": "ISO_timestamp", "id": "uuid"}`. Slicing uses `WHERE (updated_at > :t) OR (updated_at = :t AND id > :id) ORDER BY updated_at ASC, id ASC LIMIT :limit`.
- **Consequences**:
  - *Pros*: Mathematically guarantees complete, non-repeating pagination across arbitrarily large batch updates.
