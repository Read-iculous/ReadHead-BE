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
- **Decision**: Issue short-lived Access Tokens (15 minutes) and longer-lived Refresh Tokens (30 days) with token rotation on refresh, atomic Redis distributed locking (`lock:refresh:{token_hash}`), and a 30-second concurrency grace period. Database-backed token tracking allows immediate session revocation.
- **Consequences**:
  - *Pros*: Robust security profile; compromised access tokens expire rapidly; refresh tokens are rotated safely across concurrent tabs without triggering false-positive reuse detection; sessions can be invalidated instantly upon logout or administrative action.
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

## ADR-010: Real-Time Session Invalidation, Redis Downtime & Degraded Mode
- **Status**: Accepted
- **Context**: Access Tokens have a 15-minute lifetime. When an admin bans an account or a user deletes their profile, waiting for JWT expiration creates a security risk. Conversely, if Redis experiences downtime, hard-failing readiness probes (503) causes Kubernetes/Ingress to kill routing, preventing built-in database fallbacks from executing.
- **Decision**:
  1. **New Requests & Token Revocation**: Store immediate revocation markers in Redis key `revoked_users:{user_id}` with TTL = 3600 seconds whenever an account is suspended, banned, or deleted. The `get_current_user` auth dependency performs a sub-millisecond Redis check and rejects revoked users with `401 USER_SUSPENDED`.
  2. **Active Streams**: Running SSE async generators inspect user revocation status between yielded tokens. Upon detecting a revocation event, the generator immediately yields an `event: error` (`USER_SUSPENDED`) and terminates the stream.
  3. **Readiness Probe & Degraded Mode Policy**:
     - PostgreSQL is a **hard dependency**: if DB is unreachable, `/api/v1/health` returns `503 Service Unavailable`.
     - Redis is a **soft dependency with graceful degradation**: if Redis is unreachable while DB is healthy, `/api/v1/health` returns `200 OK` with status `"degraded"` (`{"status": "degraded", "checks": {"database": {"status": "healthy"}, "redis": {"status": "unhealthy"}}}`). This keeps pods in rotation while degrading non-critical features:
       - *Auth*: Bypasses Grace Cache and checks revocation directly against PostgreSQL.
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
  1. **SSE Concurrency**: Enforce a maximum of **2 active concurrent SSE streams** per user (`active_streams:{user_id}` in Redis); excess streams reject with `429 STREAM_CONCURRENCY_EXCEEDED`. Rate limits (`slowapi`) apply strictly to the initial HTTP handshake.
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

## ADR-013: Multi-Entity Sync Pagination & 30-Day Tombstone Expiration
- **Status**: Accepted
- **Context**: Synchronizing three distinct entity types (`conversations`, `highlights`, `settings`) through a single cursor created pagination ambiguity. Additionally, soft-deleted tombstones are purged after 30 days, creating a data desynchronization risk for devices offline for extended periods (> 30 days).
- **Decision**:
  1. **Multi-Entity Pagination**: Standardize `POST /api/v1/sync/pull` to return independent Composite Cursors per entity group:
     ```json
     "next_cursors": {
       "conversations": "c_base64...",
       "highlights": "h_base64...",
       "settings": "s_base64..."
     }
     ```
     Alternatively, batch slicing applies `limit` across a unified timestamp change stream ordered by `(updated_at, entity_type, entity_id)` ensuring deterministic pagination without missing updates during concurrent writes.
  2. **30-Day Tombstone Expiry & Full Resync Mandate**:
     - Database cleans up soft-deleted records (`is_deleted = TRUE`) older than 30 days.
     - If an offline client attempts an incremental sync with a cursor older than 30 days (`cursor_timestamp < NOW() - INTERVAL '30 days'`), the backend rejects the pull with `410 CURSOR_EXPIRED` and payload `{"requires_full_sync": true}`.
     - The client extension must wipe its local cache and perform a full initial resynchronization, preventing stale deleted records from persisting locally forever.
- **Consequences**:
  - *Pros*: Guarantees data consistency across long-dormant devices and clear pagination semantics across multiple entity types.

---

## ADR-014: Database Session Lifecycle Decoupling & Post-Stream Write Order
- **Status**: Accepted
- **Context**: SSE streams can take 15–45 seconds. Holding database connections across streaming exhausts pools. Furthermore, if `event: done` is dispatched to the client before the database transaction commits the assistant message, a database commit failure would cause the client to display success while the message is permanently lost on page reload.
- **Decision**: Decouple the database session lifecycle into strictly ordered phases:
  1. **Phase 1 (Pre-stream DB Transaction)**:
     - Check out transient DB session.
     - Authenticate user, decrypt BYOK key, verify tab session ownership.
     - If standard mode: Create conversation (if new) and insert `user message` into `messages` table. Commit transaction and close DB session.
  2. **Phase 2 (Streaming Loop - Zero DB Connection)**:
     - Stream LLM tokens via SSE (`event: start`, `event: token`, `event: citation`).
     - Inspect Redis cancellation flags without DB connection.
  3. **Phase 3 (Post-stream DB Commit BEFORE Event Done)**:
     - Stream generation finishes from LLM.
     - Check out fresh transient DB session.
     - Insert `assistant message`, increment `conversation.version = version + 1`, update `conversation.updated_at = NOW()`.
     - Commit DB transaction.
     - **Only after DB commit successfully finishes**, dispatch `event: done` to client.
     - **Failure Handling**: If the database commit fails, do NOT send `event: done`. Instead, dispatch `event: error` with code `PERSISTENCE_FAILED`. The client keeps the assistant reply in local memory/UI and displays a retry persistence prompt.
  4. **Privacy Mode**: Skip DB writes in Phase 1 and Phase 3 entirely; dispatch `event: done` immediately after LLM finishes streaming.
- **Consequences**:
  - *Pros*: Zero pool starvation, guaranteed message persistence before client receives success signal, clear error handling on storage failures.
