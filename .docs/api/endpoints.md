# API Endpoints Specification

Base URL: `/api/v1`

### Response Envelope Conventions
- **Standard Success**: `{"data": {...}, "message": "Optional message"}`
- **List / Paginated**: `{"data": {"items": [...], "total": 100, "page": 1, "page_size": 20, "total_pages": 5}}`
- **Error Response**: `{"detail": "Human-readable error", "code": "ERROR_CODE", "field": null}`
- **Envelope Exceptions**:
  1. `204 No Content`: Empty response body (Logout, Deletions).
  2. `GET /api/v1/health`: Raw JSON object (unwrapped) for monitoring compatibility (Kubernetes, Prometheus).
  3. `POST /api/v1/ai/stream`: Server-Sent Events stream (`text/event-stream`).

---

## 1. System Health & Diagnostics (`/api/v1/health` — Feature L)

### 1.1 GET `/api/v1/health`
- **Description**: Public health probe for uptime, database connectivity, and Redis cache status.
- **Auth**: Public
- **Response**: `200 OK` (when all dependencies healthy) or `503 Service Unavailable` (when DB or Redis down)
  ```json
  {
    "status": "healthy",
    "environment": "development",
    "version": "0.1.0",
    "uptime_seconds": 3600,
    "checks": {
      "database": { "status": "healthy", "latency_ms": 1.2 },
      "redis": { "status": "healthy", "latency_ms": 0.5 }
    },
    "timestamp": "2026-11-21T00:00:00Z"
  }
  ```
- **Failure Example (503 Service Unavailable)**:
  ```json
  {
    "status": "unhealthy",
    "environment": "development",
    "version": "0.1.0",
    "checks": {
      "database": { "status": "unhealthy", "error": "Connection refused" },
      "redis": { "status": "healthy", "latency_ms": 0.5 }
    },
    "timestamp": "2026-11-21T00:00:00Z"
  }
  ```

---

## 2. Authentication & Session (`/api/v1/auth` — Feature A)

### 2.1 POST `/api/v1/auth/register`
- **Description**: Register a new user via email and password.
- **Auth**: Public
- **Request Body**:
  ```json
  {
    "email": "user@example.com",
    "password": "SecurePassword123!",
    "full_name": "John Doe"
  }
  ```
- **Response**: `201 Created`
  ```json
  {
    "data": {
      "id": "c8a417df-1b4e-4b6e-a2b1-8b9f12345678",
      "email": "user@example.com",
      "full_name": "John Doe",
      "role": "user",
      "status": "active",
      "created_at": "2026-11-21T00:00:00Z"
    }
  }
  ```

### 2.2 POST `/api/v1/auth/login`
- **Description**: Authenticate with email and password.
- **Auth**: Public
- **Request Body**: `{"email": "user@example.com", "password": "SecurePassword123!"}`
- **Response**: `200 OK`
  ```json
  {
    "data": {
      "access_token": "jwt...",
      "refresh_token": "jwt...",
      "token_type": "bearer",
      "expires_in": 3600
    }
  }
  ```

### 2.3 POST `/api/v1/auth/oauth/google`
- **Description**: Login/Register via Google Identity ID Token. Auto-links with existing email if previously registered via password.
- **Auth**: Public
- **Request Body**: `{"id_token": "google_jwt_identity_token"}`
- **Response**: `200 OK`
  ```json
  {
    "data": {
      "access_token": "jwt...",
      "refresh_token": "jwt...",
      "token_type": "bearer",
      "expires_in": 3600
    }
  }
  ```

### 2.4 POST `/api/v1/auth/oauth/github`
- **Description**: Login/Register via GitHub OAuth2 Authorization Code.
- **Auth**: Public
- **Request Body**: `{"code": "github_auth_code"}`
- **Response**: `200 OK`
  ```json
  {
    "data": {
      "access_token": "jwt...",
      "refresh_token": "jwt...",
      "token_type": "bearer",
      "expires_in": 3600
    }
  }
  ```

### 2.5 POST `/api/v1/auth/refresh`
- **Description**: Rotate refresh token and issue new token pair. Protected with 30s grace period against concurrent multi-tab refresh races.
- **Auth**: Public
- **Request Body**: `{"refresh_token": "jwt..."}`
- **Response**: `200 OK`
  ```json
  {
    "data": {
      "access_token": "jwt...",
      "refresh_token": "jwt...",
      "token_type": "bearer",
      "expires_in": 3600
    }
  }
  ```

### 2.6 POST `/api/v1/auth/logout`
- **Description**: Revoke current refresh token session.
- **Auth**: Required
- **Request Body**: `{"refresh_token": "jwt..."}`
- **Response**: `204 No Content`

---

## 3. User & Settings (`/api/v1/users` — Features A, B, G)

### 3.1 GET `/api/v1/users/me`
- **Description**: Get current user profile and linked accounts.
- **Auth**: Required
- **Response**: `200 OK`
  ```json
  {
    "data": {
      "id": "c8a417df-1b4e-4b6e-a2b1-8b9f12345678",
      "email": "user@example.com",
      "full_name": "John Doe",
      "avatar_url": null,
      "role": "user",
      "status": "active",
      "is_verified": false,
      "created_at": "2026-11-21T00:00:00Z"
    }
  }
  ```

### 3.2 DELETE `/api/v1/users/me`
- **Description**: Delete user account and cascade delete all personal data (`FR-HIS-07`).
- **Auth**: Required
- **Request Body**: `{"confirmation": "DELETE_ACCOUNT", "password": "..."}`
- **Response**: `204 No Content`

### 3.3 GET `/api/v1/users/me/settings`
- **Description**: Get preferences, accessibility profile, proactive assistance, and privacy settings.
- **Auth**: Required
- **Response**: `200 OK`
  ```json
  {
    "data": {
      "default_provider": "gemini",
      "default_model": "gemini-1.5-flash",
      "target_language": "vi",
      "explanation_level": "standard",
      "accessibility_profile": {
        "dyslexia_font": true,
        "font_size_delta": 2,
        "line_spacing": 1.6,
        "bionic_reading": false,
        "high_contrast": false
      },
      "proactive_assistance_enabled": true,
      "proactive_sensitivity": "medium",
      "data_protection_mode": true,
      "privacy_mode_enabled": false,
      "blacklisted_domains": ["*.bank.com", "internal.corp"],
      "version": 1
    }
  }
  ```

### 3.4 PATCH `/api/v1/users/me/settings`
- **Description**: Update user preferences or accessibility settings. Requires optimistic version lock.
- **Auth**: Required
- **Request Body**: Partial settings object including `"version": 1`.
- **Response**: `200 OK` (Updated settings object with incremented version)

---

## 4. User API Keys (BYOK Vault) (`/api/v1/api-keys` — Feature C)

### 4.1 GET `/api/v1/api-keys`
- **Description**: List user's registered AI providers and masked key previews.
- **Auth**: Required
- **Response**: `200 OK`

### 4.2 POST `/api/v1/api-keys`
- **Description**: Add or update an API key for a provider (UPSERT behavior). Validates key via ping before saving (`FR-KEY-03`). If a key already exists for the provider, it is atomically replaced only if the new key passes validation; if validation fails, the existing key remains intact. Key is encrypted at rest using AES-256-GCM.
- **Auth**: Required
- **Request Body**:
  ```json
  {
    "provider": "openai",
    "api_key": "sk-realplaintextkeyhere",
    "set_active": true
  }
  ```
- **Response**: `201 Created` `{"data": {"provider": "openai", "key_hint": "sk-...keyh", "is_active": true}}`

### 4.3 DELETE `/api/v1/api-keys/{provider}`
- **Description**: Remove an API key for a specific provider.
- **Auth**: Required
- **Response**: `204 No Content`

### 4.4 POST `/api/v1/api-keys/{provider}/validate`
- **Description**: Test if the stored key is valid by sending a ping check.
- **Auth**: Required
- **Response**: `200 OK` `{"data": {"valid": true, "message": "Key validated successfully"}}`

---

## 5. AI Reading Assistant & Privacy (`/api/v1/ai` — Features E, G, H)

### 5.1 POST `/api/v1/ai/check-sensitive` (Feature H Pre-flight Check)
- **Description**: Pre-flight inspection for sensitive credentials or PII across 100% of outbound text before sending to AI.
- **Auth**: Required
- **Request Body**: `{"text": "Text snippet to inspect..."}`
- **Response**: `200 OK`
  ```json
  {
    "data": {
      "is_sensitive": true,
      "detected_types": ["api_key", "email"],
      "redacted_preview": "sk-****... found in text",
      "blocked_by_policy": true
    }
  }
  ```

### 5.2 POST `/api/v1/ai/stream` (SSE Endpoint — Feature E)
- **Description**: Unified Server-Sent Events stream for AI tasks (Explain, Summarize, Translate, Simplify, Chat).
- **Auth**: Required
- **Headers**: `Accept: text/event-stream`
- **Tab Context & Isolation**: If `conversation_id` is supplied, the server validates that `page_url` matches the original context. If mismatched, returns `400 TAB_CONTEXT_MISMATCH`.
- **Request Body**:
  ```json
  {
    "task": "explain", // "explain" | "summarize" | "translate" | "simplify" | "chat"
    "conversation_id": "uuid-optional",
    "tab_id": 101, // Tab isolation guarantee (FR-CNT-05)
    "page_url": "https://example.com/article",
    "page_title": "Example Article Title",
    "selected_text": "Selected snippet to explain...",
    "page_content": "Extracted clean text content of the article (up to 100KB)...",
    "content_type": "html_article", // "html_article" | "pdf_text"
    "user_prompt": "Explain this concept in simple terms",
    "provider": "gemini",
    "model": "gemini-1.5-flash",
    "bypass_protection": false // Set true only if user confirmed override
  }
  ```
- **SSE Stream Output**:
  ```text
  event: start
  data: {"conversation_id": "uuid", "message_id": "uuid"}

  event: token
  data: {"content": "This ", "index": 0}

  event: token
  data: {"content": "paragraph means...", "index": 1}

  event: citation
  data: {"source_id": "p-14", "text_snippet": "Neural networks process data in layers", "is_grounded": true, "confidence": 0.95}

  event: done
  data: {"message_id": "uuid", "finish_reason": "stop", "total_tokens": 142, "provider": "gemini", "model": "gemini-1.5-flash"}

  event: error
  data: {"code": "UPSTREAM_QUOTA_EXCEEDED", "detail": "Your Gemini API quota has been exhausted. Check Google AI Studio."}
  ```
- **Error & Disconnect Handling**:
  - If an error occurs, the stream emits `event: error` and closes immediately. **No `done` event is sent after `error`**.
  - If the client disconnects or closes the tab while generation is in progress, partial tokens received are saved to `messages` with `uncertainty_flag = true` and `grounding_notes = 'interrupted_by_client'` to prevent data loss.

### 5.3 POST `/api/v1/ai/proactive-suggest` (Feature G)
- **Description**: Generates an unobtrusive proactive hint when a user slows down or rereads a complex section.
- **Auth**: Required
- **Request Body**:
  ```json
  {
    "page_url": "https://example.com/article",
    "paragraph_text": "Complex academic or technical paragraph text...",
    "dwell_time_seconds": 25,
    "bypass_protection": false
  }
  ```
- **Response**: `200 OK`
  ```json
  {
    "data": {
      "has_suggestion": true,
      "suggestion_type": "key_concept",
      "hint": "This paragraph introduces Quantum Decoherence. Would you like a brief explanation?",
      "suggested_action": "explain"
    }
  }
  ```

### 5.4 POST `/api/v1/ai/feedback` (BR-15 — Evaluation & User Feedback)
- **Description**: Submit a helpful/unhelpful rating or inaccuracy report for an AI response.
- **Auth**: Required (Message must belong to a conversation owned by the authenticated user)
- **Duplicate Handling**: Submitting feedback again for the same `(user_id, message_id)` atomically updates the existing rating.
- **Request Body**:
  ```json
  {
    "message_id": "uuid",
    "rating": "unhelpful", // "helpful" | "unhelpful"
    "report_reason": "inaccurate", // "inaccurate" | "hallucination" | "harmful" | "other"
    "comment": "The translation altered the legal meaning of clause 3"
  }
  ```
- **Response**: `201 Created`

---

## 6. Comprehension Questions & Quizzes (`/api/v1/quiz` — Feature F)

### 6.1 POST `/api/v1/quiz/generate`
- **Description**: Generate 3-5 comprehension quiz questions based on article content. Answers are hidden from the response payload.
- **Auth**: Required
- **Request Body**:
  ```json
  {
    "page_url": "https://example.com/article",
    "page_text": "Article content to test...",
    "bypass_protection": false
  }
  ```
- **Response**: `200 OK`
  ```json
  {
    "data": {
      "quiz_id": "uuid",
      "questions": [
        {
          "question_id": 1,
          "question_text": "What is the primary role of transformer attention?",
          "options": ["Filter noise", "Weight token relationships", "Compress text", "Tokenize words"]
        }
      ]
    }
  }
  ```

### 6.2 POST `/api/v1/quiz/{quiz_id}/submit`
- **Description**: Submit user's selected answers for grading and receive explanations.
- **Auth**: Required
- **Request Body**: `{"answers": {"1": 1, "2": 0, "3": 2}}`
- **Response**: `200 OK`
  ```json
  {
    "data": {
      "score": 3,
      "total": 3,
      "review": [
        {
          "question_id": 1,
          "selected_option": 1,
          "correct_option": 1,
          "is_correct": true,
          "explanation": "Paragraph 2 explicitly states that attention weights token relationships."
        }
      ]
    }
  }
  ```

---

## 7. Conversations, Reading History & Highlights (`/api/v1/conversations` & `/api/v1/reading` — Feature I)

### 7.1 GET `/api/v1/conversations`
- **Description**: List user's reading chat conversations.
- **Auth**: Required
- **Query Params**: `page=1&page_size=20&search=keyword`
- **Response**: `200 OK` `{"data": {"items": [...], "total": 15}}`

### 7.2 GET `/api/v1/conversations/{id}/messages`
- **Description**: Get message history for a specific conversation.
- **Auth**: Required
- **Query Params**: `page=1&limit=50&order=asc`
- **Response**: `200 OK` `{"data": {"items": [...]}}`

### 7.3 DELETE `/api/v1/conversations/{id}`
- **Description**: Soft delete a specific conversation session and its messages (`FR-HIS-04`). Generates a sync tombstone.
- **Auth**: Required
- **Response**: `204 No Content`

### 7.4 POST `/api/v1/reading/history`
- **Description**: Record a read article with dwell time and optional cached summary. Blocked if Privacy Mode is active.
- **Auth**: Required
- **Request Body**:
  ```json
  {
    "page_url": "https://example.com/article",
    "page_title": "Article Title",
    "reading_time_seconds": 45,
    "cached_summary": "Optional summary..."
  }
  ```
- **Response**: `201 Created`

### 7.5 GET `/api/v1/reading/history`
- **Description**: List browsing and reading history with pagination and search.
- **Auth**: Required
- **Query Params**: `page=1&limit=20&search=keyword`
- **Response**: `200 OK` `{"data": {"items": [...], "total": 35}}`

### 7.6 DELETE `/api/v1/reading/history`
- **Description**: Clear entire browsing/reading history for the account (`FR-HIS-05`). Does not delete account or API keys.
- **Auth**: Required
- **Response**: `204 No Content`

### 7.7 POST `/api/v1/reading/highlights` & GET `/api/v1/reading/highlights`
- **Description**: Create and list saved text highlights and personal notes.
- **Auth**: Required
- **POST Request Body**:
  ```json
  {
    "page_url": "https://example.com/article",
    "highlighted_text": "Important text passage",
    "user_note": "Remember for research paper",
    "color": "yellow"
  }
  ```
- **Response**: `201 Created` `{"data": HighlightObject}`

---

## 8. Multi-Device Synchronization (`/api/v1/sync` — Feature J)

### 8.1 POST `/api/v1/sync/pull`
- **Description**: Pull changes updated on other devices since client's cursor timestamp. Includes soft-deleted records as tombstones.
- **Auth**: Required
- **Request Body**:
  ```json
  {
    "cursor": "2026-11-21T00:00:00.000Z",
    "limit": 100
  }
  ```
- **Response**: `200 OK`
  ```json
  {
    "data": {
      "updated_conversations": [...],
      "updated_highlights": [...],
      "updated_settings": {...},
      "next_cursor": "2026-11-21T00:05:00.000Z",
      "has_more": false
    }
  }
  ```

### 8.2 POST `/api/v1/sync/push`
- **Description**: Push local batch changes. Returns `409 SYNC_CONFLICT` if optimistic lock versions do not match.
- **Auth**: Required
- **Request Body**:
  ```json
  {
    "mutations": [
      {
        "entity_type": "conversation",
        "action": "update",
        "entity_id": "uuid",
        "base_version": 2,
        "payload": { "title": "Updated Title" }
      }
    ]
  }
  ```
- **Response**: `200 OK` or `409 Conflict` (contains server version and conflict details).

---

## 9. Admin Telemetry & Management (`/api/v1/admin` — Role `admin` Only)

### 9.1 GET `/api/v1/admin/telemetry`
- **Description**: Aggregated operational metrics and upstream provider distribution. Zero personal user reading content is visible.
- **Auth**: Required (Role `admin`)
- **Query Params**: `timeframe=24h` (`24h`, `7d`, `30d`)
- **Response**: `200 OK`
  ```json
  {
    "data": {
      "total_requests": 14205,
      "provider_split": {
        "gemini": 0.58,
        "openai": 0.28,
        "claude": 0.14
      },
      "error_rate": 0.012,
      "avg_latency_ms": 680
    }
  }
  ```

### 9.2 GET `/api/v1/admin/users`
- **Description**: List user accounts with role, status, and last activity timestamps.
- **Auth**: Required (Role `admin`)
- **Query Params**: `page=1&limit=50&status=active`
- **Response**: `200 OK`
  ```json
  {
    "data": {
      "items": [
        {
          "id": "uuid",
          "email": "user@example.com",
          "full_name": "Nguyen Van A",
          "role": "user",
          "status": "active",
          "created_at": "2026-11-14T08:00:00Z"
        }
      ],
      "total": 128
    }
  }
  ```

### 9.3 PATCH `/api/v1/admin/users/{id}/status`
- **Description**: Update user account status (e.g. suspend or ban).
- **Auth**: Required (Role `admin`)
- **Request Body**: `{"status": "suspended"}` // "active" | "suspended" | "banned"
- **Response**: `200 OK`
  ```json
  {
    "data": {
      "user_id": "uuid",
      "new_status": "suspended"
    }
  }
  ```

### 9.4 GET `/api/v1/admin/feedback`
- **Description**: Retrieve user satisfaction logs and categorized problem reports (BR-15).
- **Auth**: Required (Role `admin`)
- **Query Params**: `page=1&limit=50`
- **Response**: `200 OK`
  ```json
  {
    "data": {
      "items": [
        {
          "id": "uuid",
          "message_id": "uuid",
          "rating": "unhelpful",
          "report_reason": "inaccurate",
          "comment": "Paragraph translation altered legal context",
          "created_at": "2026-11-20T14:30:00Z"
        }
      ],
      "total": 15
    }
  }
  ```
