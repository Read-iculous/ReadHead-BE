# Architecture Decision Records (ADRs)

## ADR-001: Backend-Mediated AI Calls with BYOK Model
- **Status**: Accepted
- **Context**: The browser extension could either call AI providers directly with user keys or route through the backend.
- **Decision**: Route all AI calls through the ReadHead backend while having users supply their own API keys (BYOK).
- **Consequences**:
  - *Pros*: Centralized prompt engineering, privacy filters, token usage diagnostics, audit trails, and multi-turn history persistence without bloating the extension.
  - *Cons*: Backend handles streaming traffic and must guarantee zero-knowledge security for stored keys.

---

## ADR-002: Server-Sent Events (SSE) for Real-Time AI Generation
- **Status**: Accepted
- **Context**: AI generation can take 5-20 seconds. Users need instant visual feedback. We evaluated WebSockets vs SSE vs standard HTTP.
- **Decision**: Adopt Server-Sent Events (`text/event-stream`) for AI streaming endpoints.
- **Consequences**:
  - *Pros*: Simple, runs over standard HTTP/HTTPS, natively supported by browser `EventSource` and `fetch` with readable streams, avoids WebSocket connection state management complexity.
  - *Cons*: One-way communication from server to client per request (sufficient for prompt -> stream responses).

---

## ADR-003: Symmetric AES-256 Encryption for User API Keys
- **Status**: Accepted
- **Context**: The backend needs to decrypt user API keys to make upstream calls on their behalf, so one-way hashing (like bcrypt) cannot be used.
- **Decision**: Store API keys encrypted using AES-256-GCM with a secret master key stored strictly in environment variables (`ENCRYPTION_MASTER_KEY`).
- **Consequences**:
  - *Pros*: Strong cryptographic security at rest. If the database leaks, keys remain unreadable without the environment master key.
  - *Cons*: Key rotation requires an operational script to re-encrypt existing keys.

---

## ADR-004: Dual JWT Token Architecture (Access + Refresh Tokens)
- **Status**: Accepted
- **Context**: Extension users expect long-lived sessions without having to re-authenticate daily, while security requires short-lived access tokens.
- **Decision**: Issue short-lived Access Tokens (30-60 minutes) and longer-lived Refresh Tokens (14-30 days) with database-backed token revocation / session tracking.
- **Consequences**:
  - *Pros*: Robust security profile; compromised access tokens expire rapidly; refresh tokens can be invalidated upon logout or suspicious activity.
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
- **Decision**: Implement a pre-flight privacy check on the backend (and mirrored on the client) that scans outbound text against regex and heuristic patterns. By default, transmission is blocked with a 400 `SENSITIVE_DATA_DETECTED` response containing redacted excerpts. Users can review and explicitly override with `bypass_protection: true`.
- **Consequences**:
  - *Pros*: Guarantees data privacy compliance before outbound external API calls occur.
  - *Cons*: Slight latency overhead for regex scanning on large page extracts (mitigated by bounded token window inspection).

---

## ADR-007: Optimistic Concurrency Control for Multi-Device Sync (Feature J)
- **Status**: Accepted
- **Context**: Users can read on multiple machines (e.g. laptop and desktop). Concurrent edits to conversations or settings could cause silent data loss if "last-write-wins" is used naively.
- **Decision**: Introduce integer `version` columns on synchronized records. If a sync push contains a base version lower than the server's current version, the server raises a `SYNC_CONFLICT` error with both versions instead of silently overwriting.
- **Consequences**:
  - *Pros*: Strictly complies with `FR-SYN-05` ("System SHALL NOT silently overwrite preserved data").
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
