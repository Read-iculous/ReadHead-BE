# Database Relationships & Entity-Relationship Diagram (ERD)

## 1. Entity-Relationship Diagram

```mermaid
erDiagram
    users ||--o{ oauth_accounts : "has"
    users ||--o{ refresh_tokens : "owns"
    users ||--o{ user_api_keys : "manages"
    users ||--|| user_settings : "configures"
    users ||--o{ conversations : "initiates"
    users ||--o{ reading_history : "logs"
    users ||--o{ highlights : "creates"
    users ||--o{ quiz_records : "takes"
    users ||--o{ ai_feedback : "submits"

    conversations ||--o{ messages : "contains"
    messages ||--o{ ai_feedback : "receives"

    users {
        uuid id PK
        string email UK
        string hashed_password
        string full_name
        boolean is_active
        datetime created_at
    }

    oauth_accounts {
        uuid id PK
        uuid user_id FK
        string provider
        string provider_user_id
    }

    refresh_tokens {
        uuid id PK
        uuid user_id FK
        string token_hash
        boolean is_revoked
        datetime expires_at
    }

    user_api_keys {
        uuid id PK
        uuid user_id FK
        string provider
        text encrypted_key
        string key_hint
        boolean is_active
    }

    user_settings {
        uuid id PK
        uuid user_id FK
        string default_provider
        string default_model
        string target_language
        jsonb accessibility_profile
        boolean proactive_assistance_enabled
        boolean data_protection_mode
        boolean privacy_mode_enabled
        jsonb blacklisted_domains
        integer version
    }

    conversations {
        uuid id PK
        uuid user_id FK
        string title
        text page_url
        string page_title
        integer version
        boolean is_deleted
        datetime created_at
    }

    messages {
        uuid id PK
        uuid conversation_id FK
        string sender_role
        text content
        text selected_context
        string provider_used
        boolean is_grounded
        boolean uncertainty_flag
        text grounding_notes
        datetime created_at
    }

    reading_history {
        uuid id PK
        uuid user_id FK
        text page_url
        string page_title
        text cached_summary
        boolean is_bookmarked
        datetime visited_at
    }

    highlights {
        uuid id PK
        uuid user_id FK
        text page_url
        text highlighted_text
        text user_note
        string color
        integer version
        boolean is_deleted
        datetime created_at
    }

    quiz_records {
        uuid id PK
        uuid user_id FK
        text page_url
        jsonb questions_payload
        jsonb user_answers
        integer score
        datetime created_at
    }

    ai_feedback {
        uuid id PK
        uuid user_id FK
        uuid message_id FK
        string rating
        string report_reason
        text comment
        datetime created_at
    }
```

## 2. Foreign Key & Cascade Policies
- **User Cascade**: When a `user` is deleted, all dependent records (`oauth_accounts`, `refresh_tokens`, `user_api_keys`, `user_settings`, `conversations`, `reading_history`, `highlights`, `quiz_records`, `ai_feedback`) are **CASCADED** (`ON DELETE CASCADE`).
- **Conversation Cascade**: When a `conversation` is deleted, child `messages` are **CASCADED** (`ON DELETE CASCADE`).
- **Message Cascade**: When a `message` is deleted, its `ai_feedback` is **CASCADED**.
- **Index Recommendations**:
  - `users(email)`: Unique index.
  - `user_api_keys(user_id, provider)`: Unique index.
  - `reading_history(user_id, visited_at DESC)`: B-tree index for efficient pagination.
  - `highlights(user_id, page_url)`: B-tree index for page-level highlight retrieval.
  - `conversations(user_id, updated_at DESC)`: Index for recent conversation lookups.
  - `messages(conversation_id, created_at ASC)`: Chronological retrieval.
  - `quiz_records(user_id, created_at DESC)`: Historical quiz reviews.
