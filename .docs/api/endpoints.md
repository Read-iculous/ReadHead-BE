# API Endpoints Specification

Base URL: `/api/v1`

All responses (except streaming SSE) follow standard JSON envelopes:
- **Success**: `{"data": {...}, "message": "Optional success message"}`
- **List / Paginated**: `{"data": [...], "total": 100, "page": 1, "page_size": 20, "total_pages": 5}`
- **Error**: `{"detail": "Error description", "code": "ERROR_CODE", "field": null}`

---

## 1. System Health & Diagnostics (`/api/v1/health` — Feature L)

### 1.1 GET `/api/v1/health`
- **Description**: Public health probe for uptime, database connectivity, and environment status.
- **Auth**: Public
- **Response**: `200 OK`
  ```json
  {
    "status": "healthy",
    "database": "connected",
    "version": "1.0.0",
    "timestamp": "2026-11-15T08:00:00Z"
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

### 2.2 POST `/api/v1/auth/login`
- **Description**: Authenticate with email and password.
- **Auth**: Public
- **Request Body**: `{"email": "user@example.com", "password": "SecurePassword123!"}`
- **Response**: `200 OK` `{"data": {"access_token": "jwt...", "refresh_token": "jwt...", "token_type": "bearer"}}`

### 2.3 POST `/api/v1/auth/oauth/google`
- **Description**: Login/Register via Google OAuth2 ID Token or Auth Code.
- **Auth**: Public
- **Request Body**: `{"token": "google_id_token_or_code"}`
- **Response**: `200 OK`

### 2.4 POST `/api/v1/auth/oauth/github`
- **Description**: Login/Register via GitHub OAuth2 Authorization Code.
- **Auth**: Public
- **Request Body**: `{"code": "github_auth_code"}`
- **Response**: `200 OK`

### 2.5 POST `/api/v1/auth/refresh`
- **Description**: Exchange valid refresh token for new access token.
- **Auth**: Public
- **Request Body**: `{"refresh_token": "jwt..."}`
- **Response**: `200 OK` `{"data": {"access_token": "jwt...", "token_type": "bearer"}}`

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
- **Description**: Add or update an API key for a provider. Tests key validity before saving (`FR-KEY-03`). Key is encrypted with AES-256.
- **Auth**: Required
- **Request Body**:
  ```json
  {
    "provider": "openai",
    "api_key": "sk-realplaintextkeyhere",
    "set_active": true
  }
  ```
- **Response**: `201 Created`

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
- **Description**: Pre-flight inspection for sensitive credentials or PII before sending text to AI.
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
- **Description**: Unified Server-Sent Events stream for AI tasks (Explain, Summarize, Translate, Simplify, Chat, Quiz).
- **Auth**: Required
- **Headers**: `Accept: text/event-stream`
- **Request Body**:
  ```json
  {
    "task": "explain", // "explain" | "summarize" | "translate" | "simplify" | "chat" | "quiz"
    "conversation_id": "uuid-optional",
    "tab_id": "tab-101", // Tab isolation guarantee (FR-CNT-05)
    "page_url": "https://example.com/article",
    "page_title": "Example Article Title",
    "selected_text": "Selected snippet to explain...",
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

  event: delta
  data: {"content": "This "}

  event: delta
  data: {"content": "paragraph means..."}

  event: metadata
  data: {"is_grounded": true, "uncertainty_flag": false, "grounding_notes": "Based on paragraph 2"}

  event: done
  data: {"finish_reason": "stop"}
  ```

### 5.3 POST `/api/v1/ai/proactive-suggest` (Feature G)
- **Description**: Generates an unobtrusive proactive hint when a user slows down or rereads a complex section.
- **Auth**: Required
- **Request Body**:
  ```json
  {
    "page_url": "https://example.com/article",
    "paragraph_text": "Complex academic or technical paragraph text...",
    "dwell_time_seconds": 25
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
- **Auth**: Required
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
- **Description**: Generate 3-5 comprehension quiz questions based on article content.
- **Auth**: Required
- **Request Body**: `{"page_url": "https://...", "page_text": "..."}`
- **Response**: `200 OK` (Quiz object with unique `quiz_id` and questions without answers revealed)

### 6.2 POST `/api/v1/quiz/{quiz_id}/submit`
- **Description**: Submit user's selected answers for grading and receive explanations.
- **Auth**: Required
- **Request Body**: `{"answers": {"1": 2, "2": 0, "3": 1}}`
- **Response**: `200 OK`
  ```json
  {
    "data": {
      "score": 3,
      "total": 3,
      "review": [
        {
          "question_id": 1,
          "selected_option": 2,
          "correct_option": 2,
          "is_correct": true,
          "explanation": "Paragraph 2 explicitly states..."
        }
      ]
    }
  }
  ```

---

## 7. Conversations & History (`/api/v1/conversations` & `/api/v1/reading` — Feature I)

### 7.1 GET `/api/v1/conversations`
- **Description**: List user's reading chat conversations.
- **Auth**: Required
- **Query Params**: `page=1&page_size=20&search=keyword`
- **Response**: `200 OK`

### 7.2 GET `/api/v1/conversations/{id}/messages`
- **Description**: Get message history for a specific conversation.
- **Auth**: Required
- **Response**: `200 OK`

### 7.3 DELETE `/api/v1/conversations/{id}`
- **Description**: Delete a specific conversation session and its messages (`FR-HIS-04`).
- **Auth**: Required
- **Response**: `204 No Content`

### 7.4 DELETE `/api/v1/reading/history`
- **Description**: Clear entire browsing/reading history for the account (`FR-HIS-05`). Does not delete account or API keys.
- **Auth**: Required
- **Response**: `204 No Content`

### 7.5 POST `/api/v1/reading/highlights` & GET `/api/v1/reading/highlights`
- **Description**: Create and list saved text highlights and notes.
- **Auth**: Required

---

## 8. Multi-Device Synchronization (`/api/v1/sync` — Feature J)

### 8.1 POST `/api/v1/sync/pull`
- **Description**: Pull changes updated on other devices since client's last sync timestamp.
- **Auth**: Required
- **Request Body**: `{"last_synced_at": "2026-11-14T20:00:00Z"}`
- **Response**: `200 OK`
  ```json
  {
    "data": {
      "updated_conversations": [...],
      "updated_highlights": [...],
      "updated_settings": {...},
      "server_timestamp": "2026-11-15T08:10:00Z"
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
