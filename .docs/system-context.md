# System Context — Intelligent Reading Assistant

## 1. Context Diagram

```
                 +----------------------------------------------+
                 |          User's Chrome Browser               |
                 |  +----------------------------------------+  |
                 |  |       ReadHead Chrome Extension        |  |
                 |  |  - Content Script (DOM & Selection)   |  |
                 |  |  - Sidepanel / Popup UI               |  |
                 |  |  - Background Service Worker          |  |
                 |  +-------------------+--------------------+  |
                 +----------------------|-----------------------+
                                        |
                            HTTPS / REST & SSE Stream
                            (JWT Bearer Authorization)
                                        |
                                        v
                 +----------------------------------------------+
                 |              ReadHead Backend (BE)           |
                 |                 (FastAPI App)                |
                 |  +----------------------------------------+  |
                 |  |  - Auth & Account Management           |  |
                 |  |  - Encrypted User API Key Vault        |  |
                 |  |  - Unified LLM Gateway & Streaming     |  |
                 |  |  - Reading History & Chat Persistence  |  |
                 |  |  - Privacy & Domain Policy Filter      |  |
                 |  +-------------------+--------------------+  |
                 +----------------------|-----------------------+
                                        |
                    +-------------------+-------------------+
                    |                                       |
                    v                                       v
     +------------------------------+       +------------------------------+
     |     PostgreSQL + Redis       |       |    External AI Providers     |
     |  - Users & Credentials       |       |  - OpenAI (GPT-4o, etc.)     |
     |  - Encrypted Keys (AES-256)  |       |  - Google Gemini             |
     |  - Conversations & Messages  |       |  - Anthropic Claude          |
      |  - History, Prefs            |       |  (Called via User's Key)     |
     |  - Redis: Rate Limit & Cache |       |                              |
     +------------------------------+       +------------------------------+
```

## 2. Boundaries & Interfaces
- **Extension to Backend**:
  - Transport: HTTPS JSON REST for commands/queries + Server-Sent Events (`text/event-stream`) for AI generation.
  - Security: JWT Access Tokens in `Authorization: Bearer <token>` headers; Refresh Tokens stored in secure HTTP-only cookie or extension storage.
- **Backend to Database**:
  - Transport: PostgreSQL async wire protocol via `asyncpg`.
  - Pooling: SQLAlchemy AsyncEngine connection pool.
- **Backend to AI Providers**:
  - Transport: HTTPS REST/Streaming to official provider APIs.
  - Credentials: User's decrypted API key injected on a per-request basis.
