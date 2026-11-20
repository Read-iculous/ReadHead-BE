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
  - If at least one token was emitted, save the accumulated message text to `messages` with `uncertainty_flag = true` and `grounding_notes = 'interrupted_by_client'` so the user's conversation timeline is preserved upon reopening.

### [ISSUE-002] Upstream Token Limits on Long Web Pages & PDFs
- **Discovered**: 2026-11-14 (Updated: 2026-11-21)
- **Severity**: Medium
- **Scenario**: Extracting an entire Wikipedia article, technical spec, or lengthy PDF (e.g. 50+ pages) exceeds the model's optimal prompt token window, causing high latency or upstream `context_length_exceeded` errors.
- **Workaround / Solution**:
  - `ai_service` enforces an ingestion ceiling (max 100KB raw text / ~25k tokens).
  - When text exceeds the threshold, the service chunks the text into semantic sections. If the user selected a specific snippet, priority is given to the selected section plus 2 preceding and 2 following paragraphs (locality of reference), appending an executive document outline.

### [ISSUE-003] Multi-Tab Refresh Token Concurrency & Race Conditions
- **Discovered**: 2026-11-21
- **Severity**: High
- **Scenario**: A user has 5 browser tabs open with ReadHead Side Panels. After 60 minutes, the JWT Access Token expires simultaneously across all tabs. All 5 tabs concurrently fire `POST /api/v1/auth/refresh` using the exact same stored `refresh_token`.
- **Risk**: If strict token rotation immediately revokes the old refresh token on the first request, the remaining 4 requests fail with `401 REFRESH_TOKEN_REVOKED`, logging the user out abruptly.
- **Workaround / Solution**:
  - Implement a **30-second Concurrency Grace Period** in Redis / PostgreSQL.
  - When a refresh token is rotated, its SHA-256 hash is kept in an ephemeral cache for 30 seconds pointing to the newly generated token pair.
  - Subsequent requests within the 30-second window receive the same new token pair instead of being rejected.
  - Requests presenting the old token after 30 seconds are treated as Token Reuse attacks, immediately revoking all user sessions.

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
- **Scenario**: The system administrator needs to rotate `ENCRYPTION_MASTER_KEY` without corrupting user-stored API keys in `user_api_keys`.
- **Workaround / Solution**:
  - The cipher format uses explicit versioning: `v1:<nonce>:<ciphertext>:<tag>`.
  - A CLI migration script (`python -m app.cli.rotate_keys --old-key ... --new-key ...`) reads existing `v1` keys using the old master key, re-encrypts them under the new master key as `v2:...`, and updates the database atomically inside a transaction.
