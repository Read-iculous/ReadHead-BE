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
  - When cancelled: Explicitly close upstream before partial persistence; shield upstream/socket/client exits and Redis lease release with bounded AnyIO cancellation scopes (10 seconds each). Shield only cleanup, never the generation loop. `asyncio.shield()` alone does not protect resource-exit checkpoints in the already-cancelled AnyIO scope.
  - **Regression verification**: Mocked OpenAI/Claude/Gemini resources are checked for completed close operations on cancellation/early close. The SSE service is also exercised through Starlette `StreamingResponse` with ASGI 2.3 disconnects in standard and Privacy Mode.
  - **Standard Mode Exception**: If at least one token was emitted, save the accumulated message text to `messages` with `uncertainty_flag = true` and `grounding_notes = 'interrupted_by_client'` so the user's conversation timeline is preserved upon reopening.
  - **Privacy Mode Exception**: When `privacy_mode_enabled = true`, the system adheres strictly to the zero-retention contract. Zero rows are written to database `messages` or `conversations` even upon abrupt disconnect; partial tokens are discarded immediately.

### [ISSUE-002] Upstream Token Limits on Long Web Pages & PDFs
- **Discovered**: 2026-11-14 (Updated: 2026-11-21)
- **Severity**: Medium
- **Scenario**: Extracting an entire Wikipedia article, technical spec, or lengthy PDF (e.g. 50+ pages) exceeds the model's optimal prompt token window, causing high latency or upstream `context_length_exceeded` errors.
- **Workaround / Solution**:
  - `ai_service` enforces an ingestion ceiling (max 102,400 bytes UTF-8 raw text / ~25k tokens).
  - When text exceeds the threshold, the service chunks the text into semantic sections. If the user selected a specific snippet, priority is given to the selected section plus 2 preceding and 2 following paragraphs (locality of reference), appending an executive document outline.

### [ISSUE-003] Refresh Rotation Concurrency and Redis Failure
- **Severity**: High
- **Scenario**: Multiple tabs rotate the same refresh token; Redis may fail before or after a DB commit.
- **Solution**: Follow `.docs/technical/auth-flow.md` §2.3. Session-scoped grace cache, a cache recheck after lock acquisition, owner-safe Redis locks and PostgreSQL session-row locking/conditional updates prevent double rotation. A cached pair is usable only while its authoritative session is active.
- A rotated token with a missing grace result within 30 seconds returns `503 REFRESH_TEMPORARILY_UNAVAILABLE`, not an account-wide security revocation. Bounded refresh-only retries preserve drafts; an unrecoverable lost winning result requires explicit sign-in. Never automatically replay an AI request.
- Logout revokes the complete session chain and cleans all mappings in `refresh_grace_keys:{sid}`, including mappings keyed by earlier tokens.

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
- **Severity**: High
- **Risk**: Migrating before switching all writers can leave new `v1` ciphertext behind; removing `v1` then makes those records unreadable.
- **Solution**: Load both keys everywhere, switch every writer to `v2`, then migrate with conditional ciphertext updates. Verify no `v1` writers/records remain before removing the old live key. Use the complete runbook in `.docs/development/commands.md`.
- **CLI**: `python -m app.cli.rotate_keys --old-version v1 --new-version v2`.

### [ISSUE-007] Review Input and Tab-Isolation Regressions (Fixed)
- **Discovered / fixed**: 2026-11-21
- **Severity**: High for unbound conversation writes; Medium for optional filters and input validation.
- **Binding**: Two missing reading-session IDs previously compared equal, permitting writes to an unbound conversation. Existing standard-mode conversations now require matching non-null IDs before message insertion/stream admission.
- **Optional filters**: Explicit `Query(None, ...)` defaults keep reading history `search` and highlights `page_url` optional in runtime validation and OpenAPI.
- **Cursor validation**: Check JSON field types before timestamp/UUID parsing (including integer-only version). Malformed input returns `400 INVALID_SYNC_CURSOR` instead of leaking `AttributeError` as a server error.
- **Login password**: Check the 72-byte UTF-8 maximum before bcrypt to prevent multi-byte suffix truncation from authenticating a different password.
- **Regression tests**: `tests/unit/test_review_regressions.py` and `tests/unit/test_sse_cleanup.py`; offline/mocked scope, no real provider calls or database writes.

### [ISSUE-008] Missing CORS on Rate-Limit Responses (Fixed)
- **Discovered / fixed**: 2026-11-21
- **Severity**: Medium
- **Cause**: Operational middleware returned `429` before the inner CORS middleware could add browser response headers.
- **Fix**: Register operational middleware before CORS so CORS executes outside it. Preserve origin restrictions, credentials, and exposure of `Retry-After` / `X-Request-ID`.
- **Regression tests**: `tests/unit/test_cors.py` covers allowed/disallowed origins, preflight, handled auth/validation errors, and requests without Origin. `tests/integration/test_cors_rate_limit.py` optionally exercises actual Redis Lua counting with the production ASGI middleware stack; it does not query PostgreSQL or call AI providers.

### [ISSUE-009] Swagger Validation Error Schema Mismatch (Fixed)
- **Discovered / fixed**: 2026-11-21
- **Severity**: Low
- **Cause**: The custom validation handler returns `{detail: string, code, field}`, while generated OpenAPI still advertised FastAPI's default `detail: array` for status 422.
- **Fix**: Declare `ApiErrorResponse` for 422 responses at application registration. Runtime validation and its privacy-safe error payload are unchanged.
- **Verification**: A regression test compares the documented field types with an actual validation response; `tests/manual/verify_swagger_database.py` also checks the schema from a running local server.

### [ISSUE-010] Coerced Quiz Answers and Generated Indices (Fixed)
- **Discovered / fixed**: 2026-11-21
- **Severity**: Medium
- **Cause**: Pydantic converted `true`, `"1"` and `1.0` to integer `1` before grading checked the input type. An invalid submission could consume the single allowed attempt.
- **Fix**: Strict integer answer values and strict generated question IDs/correct-option indices. Invalid answer inputs return 422 without setting the stored score; invalid generated indices return a sanitized upstream error without creating a quiz.

### [ISSUE-011] Unvalidated OAuth Provider Payloads (Fixed)
- **Discovered / fixed**: 2026-11-21
- **Severity**: Medium
- **Cause**: Malformed tokeninfo/profile/email responses caused attribute/database errors or accepted invalid display metadata.
- **Fix**: Typed provider payload validation before DB access. Invalid shapes, IDs, emails, token values and metadata become `401 TOKEN_INVALID`. Preserve audience/issuer/expiry checks and verified-primary-email requirements.

### [ISSUE-012] Rate-Limit Replies Missing from Admin Counters (Fixed)
- **Discovered / fixed**: 2026-11-21
- **Severity**: Medium
- **Cause**: A direct 429 return skipped request/error/latency recording, undercounting denied requests in admin telemetry.
- **Fix**: Route early replies through the same response observer and telemetry finalizer. Keep request correlation and existing CORS wrapping intact.

### [ISSUE-013] Raw SDK Stream Transport Timeout Misclassified (Fixed)
- **Discovered / fixed**: 2026-11-21
- **Severity**: Medium
- **Cause**: Claude's installed SDK can expose a transport timeout while iterating response bytes. The generic SSE handler labeled it `UPSTREAM_AI_ERROR`.
- **Fix**: Apply the shared sanitized provider-error mapper to raw exceptions in streaming and non-streaming orchestration. Preserve `UPSTREAM_AI_TIMEOUT`; errors never emit a subsequent done event. Non-streaming request-local key/prompt references are cleared on exit.

The four follow-up issues are covered by `tests/integration/test_ai_quiz_oauth_admin.py`: actual FastAPI auth/services, PostgreSQL and Redis, installed AI SDKs, and explicitly synthetic upstream HTTP fixtures. These tests do not establish real provider model availability or real OAuth consent/login success.

### [ISSUE-014] Refresh / Moderation Lock Inversion (Fixed)
- **Severity**: High
- **Cause**: Refresh held a session lock before requesting the user FK key-share lock, while suspend/delete held the user lock and waited for sessions.
- **Fix**: Shared `lock_user` refreshes and locks the user before session/token locks for rotation, grace validation, issuance and revocation. PostgreSQL barrier tests force refresh to overlap suspension/deletion and assert both operations finish without a 500/deadlock.

### [ISSUE-015] Stale Privacy Snapshot During Content Writes (Fixed)
- **Severity**: High
- **Fix**: SSE admission and final/partial persistence re-read settings under the same user lock as settings updates. Newly private admission skips conversation/input writes and drops previously loaded persisted history from the private prompt. Final and disconnect partial writes skip assistant storage when privacy has become active. Initially private requests remain ephemeral. History logging and post-generation quiz checks also share the user lock to close the check/write race.
- **Historical data**: Input committed before a toggle is preserved; the fix prevents subsequent writes, not deletion of prior history.

### [ISSUE-016] Login Issued Sessions from a Stale Active User (Fixed)
- **Severity**: Medium
- **Fix**: Session issuance locks and repopulates the authoritative user after bcrypt/OAuth verification. A suspension/deletion committed while login waited for bcrypt is observed before creating any session/token. Thread barriers and actual PostgreSQL assertions verify that no usable session escapes revocation.

### [ISSUE-017] Provider-Only Settings Update Kept Another Provider's Model (Fixed)
- **Severity**: Medium
- **Fix**: PATCH and sync use one settings normalization function. A changed provider without an explicit model selects `DEFAULT_MODELS[provider]`; an explicit model or an unchanged provider's custom model is preserved. Tests inspect outbound model names for streaming, quiz and proactive calls with synthetic upstream HTTP.

### [ISSUE-018] Unicode Blacklist Did Not Match IDNA Hostnames (Fixed)
- **Severity**: Medium
- **Fix**: Normalize both stored/input patterns and request hostnames to the same case-folded IDNA representation, preserving wildcard semantics. Unicode/punycode, root/subdomain, trailing-dot and lookalike-host cases are covered. HTTP tests confirm blocked hosts cause neither automatic history writes nor upstream dispatch.

### [ISSUE-019] Optional Bearer Header Changed Public Auth Rate Bucket (Fixed)
- **Severity**: Medium
- **Fix**: Public login/register/OAuth/refresh always use the trusted ASGI client address, including trailing-slash redirects; authenticated endpoints retain user buckets. A real Redis counter test rotates two valid bearer tokens and an anonymous request on one client address and verifies one shared window.

### [ISSUE-020] Account-Deletion Password Overflow Reached bcrypt (Fixed)
- **Severity**: Medium
- **Fix**: Password confirmation, if supplied, is limited to 1–72 UTF-8 bytes before bcrypt. A wrong suffix after a valid 72-byte multi-byte password and a very large value both return 422 while preserving the account; the exact valid password still permits deletion.

Regression source: `tests/integration/test_concurrency_privacy_review.py` and `tests/unit/test_review_domain_policy.py`. Before the seven fixes, 17 regression cases failed on a disposable PostgreSQL 15 / Redis 7 setup; the normal-mode partial-save control passed. No new schema revision is needed for these code/validation/locking changes.

### [ISSUE-021] Reactivation Resumed a Revoked Stream (Fixed)
- **Severity**: Medium
- **Cause**: Reactivation removed the user-level marker while old DB sessions had no per-session stream marker. A suspend/reactivate sequence between tokens could therefore resume an old request.
- **Fix**: Publish sticky markers for every revoked session and retain them on reactivation; logout shares the helper. Marker TTL covers the maximum stream plus leeway even with short access-token lifetimes. Check revocation after upstream completion as well as before tokens so a suspension during the terminal frame prevents persistence/done. New logins use new session IDs and remain usable.

### [ISSUE-022] Stale Conversation History Before Admission (Fixed)
- **Severity**: Medium
- **Cause**: A previous stream could commit its answer between the first history snapshot and admission of the next request.
- **Fix**: After validating binding and acquiring the exclusive conversation lease under the user lock, query the latest turns, re-run outbound privacy checks and rebuild the prompt before writing the new input. Private prompts continue using only ephemeral input. A newly committed historical email/secret is included in the privacy scan, not silently dispatched.

### [ISSUE-023] Token-Limited Output Reported as Complete (Fixed)
- **Severity**: Medium
- **Fix**: The three request-scoped adapters expose normalized terminal metadata instead of service-side hard-coded `stop`. Output limits become `length`; SSE preserves text as an explicitly uncertain/incomplete partial answer and carries the flags plus reason to clients. Missing/unsupported terminal metadata produces an upstream error without a final write/done. Quiz/proactive completion rejects truncated/unterminated output instead of returning success or silently retrying.
- **Storage**: Existing uncertainty/grounding fields mark truncated saved text; private responses still have no content rows. No schema migration is required.

These streaming issues are exercised in `tests/integration/test_stream_review.py` with actual PostgreSQL/Redis and synthetic HTTP frames consumed by installed provider SDKs. The pre-fix run reproduced 17 failures while the existing 141 tests passed; synthetic provider text and previous-response fixtures are explicitly test data.

### [ISSUE-024] Out-of-Order Admin Marker Publication (Fixed)
- **Severity**: Medium
- **Cause**: A delayed suspend publisher could re-add the user marker after a newer activation deleted it; the reverse ordering could clear the marker of a newly suspended account.
- **Fix**: Reconcile from the latest DB user state in a fresh user-locked transaction and retain the lock during Redis publication. Subsequent status writers wait, and a late publisher no longer uses its request's stale status. Preserve the sticky per-session markers and best-effort Redis outage behavior.
- **Regression**: Pause Redis set/delete and run the opposite status operation concurrently in both orders. Verify the final DB/Redis agreement and a successful fresh stream when active.

### [ISSUE-025] Unexpected 500 Bypassed CORS and Correlation (Fixed)
- **Severity**: Medium
- **Fix**: Build the application stack with CORS and a correlation wrapper outside the framework server-error handler, with operational middleware inside that handler. Endpoint, limiter and token-parser runtime faults keep the sanitized JSON envelope, one request ID and allowed-origin CORS headers. Untrusted origins remain disallowed; no exception response is emitted twice.
- **Compatibility**: `app` remains a FastAPI subclass, preserving route registration, OpenAPI and dependency overrides.

### [ISSUE-026] Normal Stop with Empty Completion (Fixed)
- **Severity**: Medium
- **Fix**: `BaseAIProvider.generate_complete` rejects empty/whitespace-only text with `502 UPSTREAM_AI_ERROR` after normal-stop validation. Proactive never returns an empty successful hint, and no empty quiz is persisted. Existing non-empty text is preserved unchanged.
- **Regression**: Empty and whitespace provider streams with explicit normal terminal frames are exercised through the installed SDKs for all three providers, in proactive and quiz endpoints, without automatic retry.

The pre-fix regression run for these three issues had 11 failures and 167 passing tests. Source: `tests/integration/test_admin_marker_empty_completion.py` and the unexpected-error cases in `tests/unit/test_cors.py`. PostgreSQL/Redis are real disposable services; upstream HTTP and injected faults are test fixtures.

### [ISSUE-027] SSE Disconnect While Awaiting Send Skipped Generator Cleanup (Fixed)
- **Severity**: Medium
- **Cause**: Cancellation during response `send()` does not enter a generator suspended at yield; ASGI 2.4 send errors may also bypass the background lease release.
- **Fix**: A managed SSE response closes its generator and releases admission in a shielded `finally` for every exit path, including an unstarted generator. The service treats explicit generator closure as interruption, saving standard-mode partial text once and clearing request-local buffers. Already committed done responses are not rewritten; Privacy Mode still writes no content.
- **Regression**: Actual route responses with installed SDK HTTP fixtures, real PostgreSQL/Redis and controlled ASGI 2.3 cancellation / ASGI 2.4 send failures at headers, start, token and done, in both privacy modes.

### [ISSUE-028] Unicode DNS Root Dots Survived IDNA Normalization (Fixed)
- **Severity**: Medium
- **Fix**: Strip trailing ASCII dots after IDNA conversion as well as before. U+3002, U+FF0E and U+FF61 normalize to the same DNS root dot and cannot bypass host/pattern matching. Tests cover blocked AI dispatch and automatic history writes, plus host/pattern/wildcard equivalence.

### [ISSUE-029] NUL Password Reached Unsupported bcrypt Input (Fixed)
- **Severity**: Medium
- **Fix**: Shared password validation rejects NUL before bcrypt in registration/login/deletion confirmation, preserving byte bounds and optional omission for OAuth-only deletion. HTTP tests assert 422, no hash/verify invocation, no credential echo and no account deletion.

Initial reproduction: 14 failures and 188 passing tests before these fixes, with real disposable storage and synthetic provider HTTP. Additional controls subsequently include header-send failure and generator-frame closure. Regression files: `tests/integration/test_send_disconnect_domain_password.py` and `tests/unit/test_review_domain_policy.py`.


### [ISSUE-030] PostgreSQL-Incompatible Text Reached Storage (Fixed)
- **Severity**: Medium
- **Cause**: PostgreSQL rejects NUL in TEXT/VARCHAR/JSONB, but request schemas accepted it in highlights/notes and similar persisted text or query parameters.
- **Fix**: A shared validated text type rejects NUL and invalid Unicode before service writes/queries. Sync validates mutable text with the same rule and preserves atomic rollback. Invalid generated assistant/quiz text is treated as an upstream error before persistence; malformed OAuth identity text is rejected as `TOKEN_INVALID`.

### [ISSUE-031] Casefold Expanded Email Beyond Column Limit (Fixed)
- **Severity**: Medium
- **Fix**: Check the normalized `strip().casefold()` value against the 255-character bound before DB lookup/write for registration, login and OAuth. Tests cover expanding Unicode and successful registration/login at exactly 255 normalized characters.

### [ISSUE-032] Schema Enums Hid Domain Error Codes (Fixed)
- **Severity**: Medium
- **Fix**: The validation handler maps invalid sync mutation schemas to `400 INVALID_SYNC_MUTATION` and unsupported provider strings to `400 UNSUPPORTED_PROVIDER`, including path parameters and settings. Malformed JSON remains `INVALID_JSON`; wrong provider data types and unrelated enums retain generic `422 VALIDATION_ERROR`. No invalid credential/body values are echoed.

Regression source: `tests/integration/test_text_email_domain_errors.py`. Before the fixes, the first 25 added cases yielded 24 failures and one positive boundary pass, alongside 209 passing existing tests, on real disposable PostgreSQL/Redis. Provider HTTP in these checks is explicitly synthetic. These validation changes require no database migration.


### [ISSUE-033] Private Quizzes Survived Account Deletion (Fixed)
- **Severity**: Medium
- **Fix**: Atomically cache/index private quizzes by user, remove indexed and legacy unindexed owned quizzes before committing deletion, and fail with `503 SERVICE_DEGRADED` if cleanup cannot be confirmed. Quiz publication rechecks the user/session while holding deletion's user lock in both privacy modes. A request completing after deletion cannot recreate content. Redis compare-and-set grading already refuses to recreate deleted entries.
- **Regression**: Real-storage API deletion checks ownership isolation and legacy content, pauses generation before/after cache publication, and injects cleanup failure to verify no false 204 or committed account deletion.

### [ISSUE-034] Full-URL B-tree Rejected Valid Long URLs (Fixed)
- **Severity**: Medium
- **Fix**: Migration `0003_highlight_url_digest` indexes `(user_id, md5(page_url))`. Queries include digest and full URL equality to retain exact matching and user isolation. An incompressible 8,192-character valid URL can be saved and retrieved without an oversized index entry.
- **Rollback**: The old full-URL index cannot accommodate all newly valid URLs; export/remove incompatible rows before downgrade. Upgrade/downgrade/upgrade are exercised on disposable storage before tests.

### [ISSUE-035] Valid Refresh Successor Chain Was Cut at Ten Hops (Fixed)
- **Severity**: Medium
- **Fix**: Traverse cached successors while each mapping/token/session remains valid, using a visited-hash set for cycle detection rather than an arbitrary depth limit. Missing/corrupt/expired results still use the existing unavailable/revoked contract. The regression rotates twelve times and replays the original token to obtain the latest pair.

### [ISSUE-036] Sync Envelope Errors Became Mutation Errors (Fixed)
- **Severity**: Medium
- **Fix**: Only schema locations inside a numbered mutation-list element map to `400 INVALID_SYNC_MUTATION`. Missing/null/non-list/empty/oversized list envelopes stay `422 VALIDATION_ERROR`; invalid element fields retain the domain error.

### [ISSUE-037] Invalid JSON Encoding Used Generic Validation Code (Fixed)
- **Severity**: Medium
- **Fix**: Recognize JSON decoding causes wrapped by FastAPI's HTTPException and return sanitized `400 INVALID_JSON`, retaining CORS and request correlation. Invalid UTF-8 and truncated JSON are exercised through the production ASGI stack.

Regression source: `tests/integration/test_account_cache_url_refresh_errors.py`. All upstream HTTP is explicitly synthetic; PostgreSQL/Redis and application services are real. The initial long-URL fixture was one character too long and was corrected before final validation; that failed attempt is not counted as successful verification.

### [ISSUE-038] Deployment-Layer Hardening Is Outside the Application Boundary
- **Discovered**: 2026-11-27 (BE-01/BE-03 security review)
- **Severity**: Low (deployment responsibility, not an application bug)
- **Scenario**: Application-layer defences are verified — SQLAlchemy parameterization blocks SQL injection, Redis fixed-window limits block auth brute force/abuse, Pydantic `max_length` bounds every payload field, and JWT decoding pins a single HMAC algorithm. Two classes remain the reverse proxy's responsibility:
  1. **Total request body size**: there is no ASGI middleware returning `413` before Starlette parses the whole body. Per-field bounds cap business processing, but a very large JSON body is still read in full. Configure `client_max_body_size` (nginx) or an equivalent edge limit.
  2. **Network-layer DDoS** (SYN flood, volumetric traffic): the in-process/Redis application rate limiter cannot mitigate this. Use a CDN/WAF or infrastructure filtering.
  3. **Client IP behind a proxy**: public auth rate limits use `request.client.host`; Uvicorn must be started with `--proxy-headers --forwarded-allow-ips=<trusted proxies>` (or equivalent) or every client shares one rate bucket. `Dockerfile` currently runs without that flag.
- **Resolution**: Documented for deployment; no code change required for BE task acceptance. Regression evidence: 21-request login burst yielded `401` until the 20th request then `429`; SQLi payloads stayed literal strings with no DB effect; 20,000-character PII probe processed in ~1 ms.

### [ISSUE-039] Key Vault Hardening From Deep Review (Fixed)
- **Discovered**: 2026-11-27 (BE-07 deep review)
- **Severity**: Low
- **Findings & Fixes**:
  1. **Duplicate keyring material**: `ENCRYPTION_MASTER_KEYS` accepted the same key bytes under two version labels, making a rotation a silent no-op. Startup now rejects duplicate key material.
  2. **Store/delete resurrection race**: `store()` validates upstream (up to 10 s) before an unconditional UPSERT; a concurrent `DELETE /api-keys/{provider}` could be resurrected by the late commit. Both writers now serialize through a Redis mutex `lock:apikey:{user_id}:{provider}`.
  3. **Rotation abort on corrupt row**: `rotate_keys` aborted the entire migration when a single ciphertext failed decryption. It now logs `vault_rotation_skipped row=... reason=undecryptable`, excludes that row from subsequent batches, and continues; operators still must investigate skipped rows before removing the old key.
- **Regression**: `tests/unit/test_security_vault.py` covers roundtrip + fresh nonce, bit-flip tamper rejection (`ENCRYPTION_ERROR` without leaking plaintext), wrong version label, duplicate keyring rejection, and rotation migrating only decryptable rows via the CAS predicate.

### [ISSUE-040] PII Detector Missed Natural-Language Secret Phrasings (Fixed)
- **Discovered**: 2026-11-28 (BE-10 live verification)
- **Severity**: Low
- **Scenario**: The `password` pattern only matched `password=`/`password:` key-value forms. Phrasings such as "my password is Hunter2000x" passed `enforce()` undetected and would have been forwarded to the provider while `data_protection_mode` was on.
- **Fix**: Added a `password_phrase` pattern covering "(my|the) password/passphrase/pin (is|would be) <value>" with the same redaction behaviour. Key-value forms and innocent prose (dates, phone numbers, scientific text) are regression-checked in `tests/unit/test_ai_edge_paths.py`.

### [ISSUE-041] Consent Audit Log Duplicated Per Stream Request (Fixed)
- **Discovered**: 2026-11-28 (BE-10 live verification)
- **Severity**: Low
- **Scenario**: `ai_service` calls `enforce()` twice per stream (pre-check before key load, then re-check after reloading history/settings to close the privacy-flip race). Both calls logged `sensitive_content_override_confirmed`, so one user consent produced two audit lines.
- **Fix**: The pre-check now passes `audit=False`; only the authoritative re-check (and single-call paths such as quiz/proactive) emit the consent log. Verified live: exactly one JSON log line with request_id + masked user_id per bypassed stream.

### [ISSUE-042] NUL Bytes Survived Ingestion via `page_content` (Fixed)
- **Discovered**: 2026-11-28 (BE-09 test-gap closure)
- **Severity**: Low
- **Scenario**: `AiStreamRequest.selected_text` was a `PostgresText` (NUL-rejecting) but `page_content` was a plain `str`, so binary/NUL payloads entered prompt assembly and provider calls under `content_type: "pdf_text"`, contradicting the zero-binary ingestion rule.
- **Fix**: `page_content` now uses the same `PostgresText` annotation. Schema-level rejection is regression-checked in `tests/unit/test_ai_edge_paths.py`.

### [ISSUE-043] Proactive Suggest Calls the Provider on Every Eligible Dwell Event (Open)
- **Discovered**: 2026-11-28 (BE-11 live verification)
- **Severity**: Low (observation, no functional bug)
- **Scenario**: `POST /ai/proactive-suggest` invokes the LLM once per request whenever the user opted in and `dwell_time_seconds` exceeds the sensitivity threshold. A misbehaving extension retry loop can therefore spend user quota quickly; there is no per-conversation dedup or cooldown.
- **Status**: Open � acceptable for MVP because the endpoint is user-action-driven, but a short TTL cache keyed on `(user_id, paragraph hash)` is recommended before wide rollout.
