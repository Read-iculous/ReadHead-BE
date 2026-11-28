# Standard API Error Codes

## 1. Error Response Format
All non-2xx responses from ReadHead-BE follow the standardized JSON structure:

```json
{
  "detail": "Human-readable explanation of what went wrong",
  "code": "STANDARDIZED_ERROR_CODE",
  "field": "optional_name_of_invalid_field"
}
```

---

## 2. Error Code Registry

### 2.1 Authentication & Authorization (`401`, `403` — Feature A)
| HTTP Status | Error Code | Description |
|---|---|---|
| `401` | `UNAUTHORIZED` | Authentication credentials missing, invalid or malformed |
| `401` | `INVALID_CREDENTIALS` | Incorrect email or password |
| `401` | `TOKEN_EXPIRED` | Access token has expired; client should refresh |
| `401` | `TOKEN_INVALID` | Malformed or improperly signed JWT |
| `401` | `REFRESH_TOKEN_EXPIRED` | Refresh token expired; user must log in again |
| `401` | `REFRESH_TOKEN_REVOKED` | Session/token revoked by logout/security, or rotated token used outside grace; does not automatically revoke unrelated sessions |
| `401` | `USER_SUSPENDED` | Account has been suspended or banned by administrator |
| `403` | `ACCOUNT_INACTIVE` | Account has been deactivated |
| `403` | `EMAIL_NOT_VERIFIED` | Account email has not been verified. Applies to BOTH paths: password login of a registered-but-unverified account (`POST /auth/login`, response includes `can_resend: true`) and OAuth sign-in where the identity provider indicates the email is not verified (`POST /auth/oauth/google`). Resolution: `POST /auth/verify-email/resend` then `POST /auth/verify-email` |
| `403` | `FORBIDDEN_RESOURCE` | User does not own the requested resource |

### 2.2 Validation & Client Errors (`400`, `422`)
| HTTP Status | Error Code | Description |
|---|---|---|
| `422` | `VALIDATION_ERROR` | General schema validation failure, including NUL/invalid Unicode in PostgreSQL-bound text and email exceeding 255 characters after normalization; domain-specific cases below take precedence |
| `400` | `INVALID_JSON` | Malformed JSON request body |
| `400` | `OAUTH_EMAIL_MISSING` | OAuth provider account has no public or verified email address |
| `400` | `CANNOT_MODIFY_SELF_STATUS` | Administrators cannot suspend, ban, or alter their own account status |
| `400` | `LAST_ADMIN_LOCKOUT` | Suspending or banning the **last active administrator** is rejected (`PATCH /admin/users/{id}/status`, planned — BE-27). Moderating other administrators remains allowed; the last admin must always be able to act on everyone else |
| `400` | `QUIZ_ALREADY_SUBMITTED` | Quiz has already been submitted and graded; submitted quizzes cannot be retaken (no retry/reset path) |
| `400` | `UNSUPPORTED_LANGUAGE` | Unsupported language value: `ui_language` outside `{vi, en}` in `PATCH /users/me/settings`, or `target_language` outside the supported translation set (`vi`, `en`, `ja`, `zh`, `ko`, `fr`, `de`, `es`) in settings PATCH or `POST /ai/stream` |
| `409` | `EMAIL_ALREADY_EXISTS` | Registration email already registered (also `PATCH /users/me` email change) |

#### Email Verification & Password Reset (`400` — Feature A, BE-19)
Token semantics: unknown/already-consumed → `*_INVALID`; known-but-past-expiry → `*_EXPIRED`. Plaintext tokens exist only in email links; the database stores SHA-256 hashes only.
| HTTP Status | Error Code | Description |
|---|---|---|
| `400` | `VERIFICATION_TOKEN_EXPIRED` | Verification token known but past its 24h TTL (`POST /auth/verify-email`); user must request a resend |
| `400` | `VERIFICATION_TOKEN_INVALID` | Verification token unknown or already consumed (single use) (`POST /auth/verify-email`) |
| `400` | `RESET_TOKEN_EXPIRED` | Password reset token known but past its 60-minute TTL (`POST /auth/reset-password`); user must request a new link |
| `400` | `RESET_TOKEN_INVALID` | Password reset token unknown or already consumed (single use) (`POST /auth/reset-password`) |

### 2.3 Not Found (`404`)
| HTTP Status | Error Code | Description |
|---|---|---|
| `404` | `NOT_FOUND` | Unmatched route (no endpoint registered at the requested path) |
| `404` | `USER_NOT_FOUND` | User entity not found |
| `404` | `API_KEY_NOT_FOUND` | No API key found for requested provider |
| `404` | `CONVERSATION_NOT_FOUND` | Conversation session ID not found |
| `404` | `MESSAGE_NOT_FOUND` | Message ID not found. Also returned by `POST /ai/feedback` for a Privacy-Mode ephemeral message (never persisted, so the `ai_feedback.message_id` FK target does not exist) |
| `404` | `HIGHLIGHT_NOT_FOUND` | Highlight ID not found, unowned, or already tombstoned (also for `PATCH /reading/highlights/{id}` edits) |
| `404` | `QUIZ_NOT_FOUND` | Quiz ID not found, belongs to another user, or was tombstoned. Also covers ephemeral Privacy-Mode quizzes whose Redis cache entry has expired (30-minute TTL) — expiry is indistinguishable from absence |

### 2.4 Privacy & Sensitive Data (`400` — Feature H)
| HTTP Status | Error Code | Description |
|---|---|---|
| `400` | `SENSITIVE_DATA_DETECTED` | Request text contains credentials, keys, or PII. Blocked by default policy |
| `400` | `DOMAIN_BLOCKED_BY_PRIVACY`| Target domain is in user's privacy blacklist |

### 2.5 Multi-Device Synchronization & Concurrency (`409`, `410` — Feature J)
| HTTP Status | Error Code | Description |
|---|---|---|
| `409` | `SYNC_CONFLICT` | Stale version detected. Target record was updated by another device |
| `409` | `CONVERSATION_BUSY` | Conversation is actively streaming tokens in another tab session. Applies to binding (§5.5), single delete while streaming (`DELETE /conversations/{id}` — client must stop the stream first) and is surfaced as a per-row skip in bulk delete (`DELETE /conversations`) |
| `410` | `CURSOR_EXPIRED` | Cursor retention anchor older than 30 days; rebuild synced cache while preserving drafts, credentials and pending mutations |
| `400` | `INVALID_SYNC_CURSOR` | Invalid Base64url cursor, unsupported version or invalid tuple/checkpoint fields |
| `400` | `INVALID_SYNC_MUTATION` | Malformed mutation schema/payload, unsupported entity type/action, or invalid entity fields; an invalid batch is atomic and applies no changes |

### 2.6 AI Gateway & BYOK Errors (`400`, `502`, `504` — Features C & E)
| HTTP Status | Error Code | Description |
|---|---|---|
| `400` | `NO_ACTIVE_API_KEY` | User has not configured an active API key for the provider (also returned by `/ai/stream` after the default provider is removed via `DELETE /api-keys/{provider}`) |
| `400` | `KEY_VALIDATION_FAILED` | Key rejected by provider during initial validation ping (`POST /api-keys/{provider}/validate`); the provider responded and refused the key |
| `400` | `UNSUPPORTED_PROVIDER` | Unsupported provider string in body, settings or provider path; missing required fields and wrong data types remain `422 VALIDATION_ERROR` |
| `400` | `TAB_CONTEXT_MISMATCH` | Inbound request mixed conversation ID with incompatible tab context |
| `422` | `UNREPRESENTATIVE_SOURCE` | Extracted page content insufficient to generate grounded response or quiz |
| `403` | `UPSTREAM_KEY_INVALID` | Provider rejected the stored user key with an auth error while a stream was already running (`POST /ai/stream` mid-stream `event: error`); distinct from `UPSTREAM_AI_ERROR` so clients route to key management. Key is not auto-deleted |
| `502` | `UPSTREAM_AI_ERROR` | Provider API (OpenAI/Gemini/Claude) returned an error; on `POST /api-keys/{provider}/validate`, detail `"provider unreachable"` means the provider could not be reached — not that the key is bad |
| `502` | `UPSTREAM_QUOTA_EXCEEDED` | User's provider quota/credit has been exhausted |
| `504` | `UPSTREAM_AI_TIMEOUT` | Provider took too long to begin streaming |

### 2.7 Server & System Errors (`500`, `503` — Feature L)
| HTTP Status | Error Code | Description |
|---|---|---|
| `500` | `INTERNAL_SERVER_ERROR` | Unhandled runtime exception |
| `500` | `DATABASE_ERROR` | Database connection or execution failure |
| `500` | `ENCRYPTION_ERROR` | Key decryption failure (invalid master key) |
| `500` | `PERSISTENCE_FAILED` | Failed to atomically commit stream completion and assistant message to database |
| `503` | `DEPENDENCY_UNHEALTHY` | Database connection failure (hard service outage) |
| `503` | `REFRESH_TEMPORARILY_UNAVAILABLE` | Refresh lock timeout or recently rotated token with unavailable grace result; Retry-After: 1, no global logout |
| `503` | `SERVICE_DEGRADED` | Ephemeral feature temporarily unavailable due to Redis downtime |

### 2.8 Rate Limiting & Concurrency (`429` — Platform Ops & Guardrails)
| HTTP Status | Error Code | Description |
|---|---|---|
| `429` | `RATE_LIMIT_EXCEEDED` | Request rate limit exceeded for IP or user |
| `429` | `STREAM_CONCURRENCY_EXCEEDED` | Maximum active concurrent SSE streams exceeded (max 2 active streams per user) |
