# ReadHead-BE — Intelligent Reading Assistant Backend

Core backend API service powering the **Intelligent Reading Assistant**, an AI-driven Chrome Browser Extension and Web Management Portal designed under ISO/IEC/IEEE 29148:2018 standards.

---

## 🚀 Key Capabilities
- **Unified AI Gateway**: Multi-provider support (OpenAI GPT-4o, Google Gemini, Anthropic Claude) via user BYOK model.
- **Real-Time Streaming**: High-throughput Server-Sent Events (SSE) streaming for explanations, translations, summarization, and comprehension quizzes.
- **Encrypted BYOK Vault**: Symmetrical AES-256-GCM encryption at rest for user API keys.
- **Privacy & Pre-Flight Inspection**: Block outbound PII, credentials, and blacklisted domains by default.
- **Multi-Device Synchronization**: Versioned optimistic concurrency control preventing silent overwrites.
- **Admin Management & Telemetry**: Platform health monitoring, provider usage distribution, user moderation, and Redis-backed rate limiting.

---

## 🛠 Tech Stack
- **Framework**: FastAPI (Python 3.10+) with Uvicorn ASGI
- **Database**: PostgreSQL 15+ (asyncpg + SQLAlchemy 2.0 async)
- **Cache & Limiter**: Redis 7.0+ (`slowapi` + `redis-py`)
- **Migrations**: Alembic
- **Validation**: Pydantic V2

---

## 📖 Documentation
All specifications and technical design documents are located in [`.docs/`](file:///c:/Users/Asus/Desktop/ReadHead/ReadHead-BE/.docs/project-overview.md):
- [Project Overview](file:///c:/Users/Asus/Desktop/ReadHead/ReadHead-BE/.docs/project-overview.md)
- [API Endpoints](file:///c:/Users/Asus/Desktop/ReadHead/ReadHead-BE/.docs/api/endpoints.md)
- [Database Schema](file:///c:/Users/Asus/Desktop/ReadHead/ReadHead-BE/.docs/database/schema.md)
- [Architecture Overview](file:///c:/Users/Asus/Desktop/ReadHead/ReadHead-BE/.docs/architecture/overview.md)
- [Development Tasks](file:///c:/Users/Asus/Desktop/ReadHead/ReadHead-BE/.docs/development/tasks.md)
