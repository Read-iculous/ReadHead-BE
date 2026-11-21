# Known Issues & Edge Cases — ReadHead-BE

## 1. Registry Format
Entries are added here as edge cases or technical quirks are discovered during development.

---

## 2. Documented Issues & Scenarios

### [ISSUE-001] Client Disconnect & Abort During SSE Streaming
- **Discovered**: 2026-11-14 (Updated: 2026-11-21)
- **Severity**: High
- **Scenario**: A user closes the Chrome Extension side panel, refreshes the webpage, or switches tabs while an LLM streaming response is in flight. The client closes the HTTP connection abruptly.
- **Risk**: Unhandled `asyncio.CancelledError` leaking upstream streaming generators, or leaving orphaned incomplete database records.
- **Workaround / Solution**:
  - In FastAPI SSE streaming generators, wrap chunk consumption in `try ... except asyncio.CancelledError:`.
  - When cancelled: Explicitly close the upstream generator to stop consuming the user's BYOK tokens.
  - **Standard Mode Exception**: If at least one token was emitted, save the accumulated message text to `messages` with `uncertainty_flag = true` and `grounding_notes = 'interrupted_by_client'` so the user's conversation timeline is preserved upon reopening.
  - **Privacy Mode Exception**: When `privacy_mode_enabled = true`, the system adheres strictly to the zero-retention contract. Zero rows are written to database `messages` or `conversations` even upon abrupt disconnect; partial tokens are discarded immediately.

### [ISSUE-002] Upstream Token Limits on Long Web Pages & PDFs
- **Discovered**: 2026-11-14 (Updated: 2026-11-21)
- **Severity**: Medium
- **Scenario**: Extracting an entire Wikipedia article, technical spec, or lengthy PDF (e.g. 50+ pages) exceeds the model's optimal prompt token window, causing high latency or upstream `context_length_exceeded` errors.
- **Workaround / Solution**:
  - `ai_service` enforces an ingestion ceiling (max 102,400 bytes UTF-8 raw text / ~25k tokens).
  - When text exceeds the threshold, the service chunks the text into semantic sections. If the user selected a specific snippet, priority is given to the selected section plus 2 preceding and 2 following paragraphs (locality of reference), appending an executive document outline.

### [ISSUE-003] Multi-Tab Refresh Token Concurrency & Race Conditions
- **Discovered**: 2026-11-21
- **Severity**: High
- **Scenario**: A user has 5 browser tabs open with ReadHead Side Panels. After 15 minutes, the JWT Access Token expires simultaneously across all tabs. All 5 tabs concurrently fire `POST /api/v1/auth/refresh` using the exact same stored `refresh_token`.
- **Risk**: Without synchronization, the first request revokes the token in DB while the second concurrent request reads the revoked token before the Redis grace cache is populated, triggering a false-positive Token Reuse Attack and abruptly logging the user out.
- **Workaround / Solution**:
  - Implement a **Redis Distributed Lock** (`lock:refresh:{token_hash}`, TTL 5s) coupled with a **30-second Grace Period Cache**.
  - Always verify user account status (`revoked_users:{user_id}`) before returning any cached token.
  - The first tab acquires the lock, rotates the token in PostgreSQL, writes the result to `refresh_grace:{token_hash}` (30s TTL), and releases the lock.
  - Sibling tabs wait on the lock and immediately receive the cached new token pair once released without touching the database.
  - If Redis fails after the DB commit, the server falls back to returning the new token pair directly to the winning client without throwing an error.

### [ISSUE-004] Multi-Device Sync Version Collision (Feature J)
- **Discovered**: 2026-11-21
- **Severity**: Medium
- **Scenario**: User edits a conversation title on their laptop while offline, and edits the same conversation on their desktop. When both reconnect, a version collision occurs.
- **Risk**: Silent overwriting of user data violates `FR-SYN-05`.
- **Workaround / Solution**:
  - `POST /api/v1/sync/push` validates `base_version == current_record.version`.
  - On mismatch, the server refuses the mutation and responds with `409 SYNC_CONFLICT` returning:
    ```json
    {
      "code": "SYNC_CONFLICT",
      "detail": "Record was modified on another device",
      "server_record": { "id": "...", "version": 3, "payload": {...} },
      "client_version": 2
    }
    ```
  - The client UI presents a conflict resolution prompt, never silently overwriting user work.

### [ISSUE-005] Differentiating BYOK Quota Exceeded vs Platform Rate Limiting
- **Discovered**: 2026-11-21
- **Severity**: Medium
- **Scenario**: An AI request fails due to rate limits. The user does not know whether the failure is due to their personal API key balance (e.g. OpenAI credits exhausted) or ReadHead's server-level rate limiter.
- **Workaround / Solution**:
  - ReadHead server limiter returns **`429 Too Many Requests`** with header `Retry-After: 30` and code `RATE_LIMIT_EXCEEDED`.
  - Upstream provider quota exhaustion is caught by adapter exception mappers and returned as **`502 Bad Gateway`** with code `UPSTREAM_QUOTA_EXCEEDED` and a human-readable guidance message (e.g. *"Your OpenAI account has insufficient credits. Please check platform.openai.com"*).

### [ISSUE-006] Master Encryption Key Rotation Procedure
- **Discovered**: 2026-11-21
- **Severity**: Low
- **Scenario**: The system administrator needs to rotate `ENCRYPTION_MASTER_KEY` / `ENCRYPTION_MASTER_KEYS` without corrupting user-stored API keys in `user_api_keys`.
- **Workaround / Solution**:
  - The cipher format uses explicit versioning: `v1:<nonce>:<ciphertext>:<tag>`.
  - The application reads master keys from `ENCRYPTION_MASTER_KEYS` dictionary, supporting concurrent decryption across multiple versions (e.g. `v1` and `v2`).
  - A CLI migration script (`python -m app.cli.rotate_keys --old-version 1 --new-version 2`) reads existing `v1` keys using the old key version, re-encrypts them under the new master key version as `v2:...`, and updates the database atomically inside a transaction.
  - Once the migration succeeds, `CURRENT_KEY_VERSION` is bumped to `v2` and `v1` can be deprecated.
