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

---

## 3. SRS Constraint Traceability (VT-19)

Traceability of the SRS design & technology constraints (SRS §3.4, CON-01…14; verified
per VT-19 — Inspection/Analysis, High priority). For each constraint: where it is
enforced or ensured in project documentation, and its status. If no enforcement
location exists, the row says **gap** — none is invented.

| Constraint | Summary | Enforced / ensured in | Status |
|---|---|---|---|
| CON-01 | Main user UI SHALL be a Chrome Extension | Not a BE concern: `ReadHead-FE/.docs/architecture/overview.md` (Extension surfaces) and `ReadHead-FE/.docs/project-overview.md`; BE side is the client contract in `ReadHead-BE/.docs/system-context.md` and `ReadHead-FE/.docs/api/backend-contract.md` | enforced (in ReadHead-FE docs — out of BE repo scope) |
| CON-02 | UI technology SHALL be React | `ReadHead-FE/.docs/technical/tech-stack.md`; `ReadHead-FE/.docs/architecture/decisions.md` | enforced (in ReadHead-FE docs — out of BE repo scope) |
| CON-03 | Backend SHALL be Python/FastAPI (async), recorded in the ADD | `ReadHead-BE/.docs/technical/tech-stack.md`; `ReadHead-BE/.docs/architecture/decisions.md` (ADR-001 backend-mediated AI, ADR-002 SSE); `ReadHead-BE/.docs/project-overview.md` | enforced |
| CON-04 | AI Service SHALL be Python, separated as a distinct logic component from the Backend | `ReadHead-BE/.docs/architecture/components.md` §2.1 Unified AI Gateway (`app/core/ai/`) — a self-contained adapter subsystem layered under `app/services/ai_service.py`; `ReadHead-BE/.docs/architecture/decisions.md` ADR-001 | enforced (as a separate logical layer within the backend process, not a separate host) |
| CON-05 | Backend ↔ AI Service SHALL communicate via a well-defined interface; physical separation not required | `ReadHead-BE/.docs/architecture/components.md` §2.1 (adapter interface `app/core/ai/base.py`, `factory.py`); `ReadHead-BE/.docs/architecture/decisions.md` ADR-001/ADR-002 (SSE contract) | enforced |
| CON-06 | Provider integration SHALL allow swap/addition without rewriting reading features | `ReadHead-BE/.docs/architecture/components.md` §2.1 (three interchangeable provider adapters behind one interface); `ReadHead-BE/.docs/technical/dependencies.md` §1 (AI Provider SDKs); ADR-001 | enforced |
| CON-07 | Unified data-protection rule SHALL apply before sending requests to ANY supported provider | `ReadHead-BE/.docs/architecture/decisions.md` ADR-006 (pre-flight sensitive-content inspection); `ReadHead-BE/.docs/api/endpoints.md` §5.1 (`POST /ai/check-sensitive`) & §5.2 (preflight on the stream path); `ReadHead-BE/.docs/architecture/components.md` §2.2 (privacy engine) | enforced |
| CON-08 | Authentication/authorization SHALL fit the shared-service model | `ReadHead-BE/.docs/technical/auth-flow.md`; `ReadHead-BE/.docs/api/endpoints.md` §2 (auth & session); `ReadHead-BE/.docs/architecture/decisions.md` ADR-004 (JWT rotation), ADR-010 (revocation), ADR-019 (role bootstrap) | enforced |
| CON-09 | Storage, encryption, deployment, backup, recovery and secret management SHALL be recorded in the ADD | `ReadHead-BE/.docs/architecture/decisions.md` ADR-003 (AES-256-GCM keyring); `ReadHead-BE/.docs/technical/environment-variables.md` (secrets); `ReadHead-BE/.docs/development/commands.md` §5 + Zero-Downtime Rotation Runbook + Backup & Restore Runbook; `ReadHead-BE/.docs/development/deployment.md`; `ReadHead-BE/.docs/database/migrations.md` | enforced (RTO/RPO targets in the runbook are placeholders pending approval) |
| CON-10 | End users SHALL NOT be required to deploy the Backend or AI Service | `ReadHead-BE/.docs/architecture/decisions.md` ADR-001 (backend-mediated BYOK: users only configure keys in the extension); `ReadHead-BE/.docs/development/deployment.md` (deployment is an operator/project activity) | enforced by design; the hosted/production deployment story itself is not finalized for MVP |
| CON-11 | Fully offline AI SHALL NOT be an MVP requirement | `ReadHead-BE/.docs/knowledge/constraints.md` §2.1 (BYOK — no valid key ⇒ `NO_ACTIVE_API_KEY`, no AI execution); `ReadHead-BE/.docs/project-overview.md`; ADR-001 | enforced |
| CON-12 | Simulated demo features SHALL be distinguished from truly implemented functionality | `ReadHead-BE/.docs/development/implementation-status.md` (Implemented / Docs complete; NOT implemented / simulated-fixture discipline, `scope.json` mock-vs-real boundary); `ReadHead-BE/.docs/knowledge/known-issues.md` | enforced |
| CON-13 | Every external technology/service SHALL have a documented communication contract and dependency limits | `ReadHead-BE/.docs/technical/dependencies.md` (pinned SDKs, rejected-wrapper rationale); `ReadHead-BE/.docs/technical/tech-stack.md`; `ReadHead-BE/.docs/api/endpoints.md` + `ReadHead-BE/.docs/api/error-codes.md` (provider error contracts); `ReadHead-BE/.docs/technical/environment-variables.md` (outbound config) | enforced |
| CON-14 | Design decisions on API Keys, sensitive data, conversation storage and sync SHALL be explained in the ADD and linked to requirements | `ReadHead-BE/.docs/architecture/decisions.md` ADR-003 (API-key encryption), ADR-006 (sensitive data), ADR-005 (hybrid storage), ADR-013 (sync cursor & conflicts), ADR-007 (sync concurrency); requirements IDs cited inside each ADR; schema realization in `ReadHead-BE/.docs/database/schema.md` | enforced |

Review note (2026-11-29): mapping produced during the NFR-gap remediation pass
(GAP-4 / VT-19). Rows marked "in ReadHead-FE docs" are enforced in the companion
frontend repository's documentation, not in ReadHead-BE; no BE-side gap was found.
