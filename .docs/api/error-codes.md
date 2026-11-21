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
| `401` | `INVALID_CREDENTIALS` | Incorrect email or password |
| `401` | `TOKEN_EXPIRED` | Access token has expired; client should refresh |
| `401` | `TOKEN_INVALID` | Malformed or improperly signed JWT |
| `401` | `REFRESH_TOKEN_EXPIRED` | Refresh token expired; user must log in again |
| `401` | `REFRESH_TOKEN_REVOKED` | Refresh token was explicitly logged out or invalidated |
| `401` | `USER_SUSPENDED` | Account has been suspended or banned by administrator |
| `403` | `ACCOUNT_INACTIVE` | Account has been deactivated |
| `403` | `FORBIDDEN_RESOURCE` | User does not own the requested resource |

### 2.2 Validation & Client Errors (`400`, `422`)
| HTTP Status | Error Code | Description |
|---|---|---|
| `422` | `VALIDATION_ERROR` | Pydantic schema validation failure |
| `400` | `INVALID_JSON` | Malformed JSON request body |
| `400` | `CANNOT_MODIFY_SELF_STATUS` | Administrators cannot suspend, ban, or alter their own account status |
| `400` | `QUIZ_ALREADY_SUBMITTED` | Quiz has already been submitted and graded |
| `409` | `EMAIL_ALREADY_EXISTS` | Registration email already registered |

### 2.3 Not Found (`404`)
| HTTP Status | Error Code | Description |
|---|---|---|
| `404` | `USER_NOT_FOUND` | User entity not found |
| `404` | `API_KEY_NOT_FOUND` | No API key found for requested provider |
| `404` | `CONVERSATION_NOT_FOUND` | Conversation session ID not found |
| `404` | `MESSAGE_NOT_FOUND` | Message ID not found |
| `404` | `HIGHLIGHT_NOT_FOUND` | Highlight ID not found |
| `404` | `QUIZ_NOT_FOUND` | Quiz record ID not found |

### 2.4 Privacy & Sensitive Data (`400` — Feature H)
| HTTP Status | Error Code | Description |
|---|---|---|
| `400` | `SENSITIVE_DATA_DETECTED` | Request text contains credentials, keys, or PII. Blocked by default policy |
| `400` | `DOMAIN_BLOCKED_BY_PRIVACY`| Target domain is in user's privacy blacklist |

### 2.5 Multi-Device Synchronization & Concurrency (`409` — Feature J)
| HTTP Status | Error Code | Description |
|---|---|---|
| `409` | `SYNC_CONFLICT` | Stale version detected. Target record was updated by another device |
| `400` | `INVALID_SYNC_MUTATION` | Malformed mutation payload or unknown entity type |

### 2.6 AI Gateway & BYOK Errors (`400`, `502`, `504` — Features C & E)
| HTTP Status | Error Code | Description |
|---|---|---|
| `400` | `NO_ACTIVE_API_KEY` | User has not configured an active API key for the provider |
| `400` | `KEY_VALIDATION_FAILED` | Key rejected by provider during initial validation ping |
| `400` | `UNSUPPORTED_PROVIDER` | Requested provider is not implemented |
| `400` | `TAB_CONTEXT_MISMATCH` | Inbound request mixed conversation ID with incompatible tab context |
| `422` | `UNREPRESENTATIVE_SOURCE` | Extracted page content insufficient to generate grounded response or quiz |
| `502` | `UPSTREAM_AI_ERROR` | Provider API (OpenAI/Gemini/Claude) returned an error |
| `502` | `UPSTREAM_QUOTA_EXCEEDED` | User's provider quota/credit has been exhausted |
| `504` | `UPSTREAM_AI_TIMEOUT` | Provider took too long to begin streaming |

### 2.7 Server & System Errors (`500`, `503` — Feature L)
| HTTP Status | Error Code | Description |
|---|---|---|
| `500` | `INTERNAL_SERVER_ERROR` | Unhandled runtime exception |
| `500` | `DATABASE_ERROR` | Database connection or execution failure |
| `500` | `ENCRYPTION_ERROR` | Key decryption failure (invalid master key) |
| `503` | `DEPENDENCY_UNHEALTHY` | Core dependency (Database or Redis) connection failure |

### 2.8 Rate Limiting & Concurrency (`429` — Platform Ops & Guardrails)
| HTTP Status | Error Code | Description |
|---|---|---|
| `429` | `RATE_LIMIT_EXCEEDED` | Request rate limit exceeded for IP or user |
| `429` | `STREAM_CONCURRENCY_EXCEEDED` | Maximum active concurrent SSE streams exceeded (max 2 active streams per user) |
