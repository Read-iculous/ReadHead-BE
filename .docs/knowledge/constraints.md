# Project Constraints

## 1. Technical & Architectural Constraints
1. **Asynchronous Non-Blocking Execution**: Because the backend handles concurrent streaming SSE connections, any synchronous blocking I/O (e.g. `time.sleep()`, synchronous DB drivers, or synchronous HTTP clients) freezes the event loop and degrades streaming performance across all active clients.
2. **Symmetrical Envelope Key Encryption**: The server must never store user-provided API keys in plaintext. Keys are encrypted at rest with AES-256-GCM. The master encryption key must never be checked into version control and must only exist in environment configuration (`ENCRYPTION_MASTER_KEYS`, or `ENCRYPTION_MASTER_KEY` as the single-key fallback). Plaintext keys exist only ephemerally in RAM during upstream calls.
3. **Safe Diagnostic Logging (`FR-OPS-03`)**: Application logs must **never** contain plaintext user API keys, authorization tokens, or sensitive page text. Telemetry is restricted to performance metrics, sanitized error codes, and operational status.
4. **Tab-Isolated Reading Context (`FR-CNT-05~06`)**: Contexts from different browser tabs must remain completely isolated. The backend must never mix messages or DOM extracts across distinct active tab sessions.
5. **Multi-Account Browser Isolation (`FR-ACC-04`)**: When switching user accounts on the same browser, active working state must be purged to prevent cross-account data leakage.

---

## 2. Business & Operational Constraints
1. **BYOK (Bring Your Own Key) Model**: The MVP operates without a centralized paid AI pool. If a user does not provide a valid API key, the system cannot execute AI operations for that user and must return a clear `NO_ACTIVE_API_KEY` error.
2. **Prohibition of Silent Automated AI Retries (`FR-AI-10`, `FR-ERR-04`, `FR-KEY-06`)**: Under no circumstances shall the backend or extension automatically re-submit failed or pending AI requests after a network reconnect or key update. The user must explicitly initiate the retry.
3. **Separation of History Deletion vs Account Deletion (`FR-HIS-07`)**: The system must provide distinct operations for:
   - Deleting a single conversation session (`DELETE /api/v1/conversations/{id}`).
   - Clearing all reading history (`DELETE /api/v1/reading/history`).
   - Deleting the account entirely (`DELETE /api/v1/users/me`).
4. **Data Protection Mode vs History Mode (`FR-HIS-09`)**: Turning on Data Protection Mode (PII/sensitive content inspection) does **not** disable conversation history storage, and vice versa. They are independent features.
5. **Source Grounding Prioritization (`BR-12~14`)**: When answering reading questions, the system must prioritize the current page text and explicitly declare when an answer relies on external knowledge or when source evidence is insufficient.
