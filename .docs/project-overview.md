# Project Overview — Intelligent Reading Assistant (ReadHead-BE)

## 1. Executive Summary
**ReadHead-BE** is the core backend API service powering the **Intelligent Reading Assistant**, an AI-driven Chrome Browser Extension designed to help users comprehend, summarize, translate, and interact with web articles and digital reading materials in real time.

The system is specified according to ISO/IEC/IEEE 29148:2018 standards and documented across BRS, StRS, OpsCon, SyRS, and SRS. The backend serves as the secure orchestrator between the browser extension client, the PostgreSQL database, and external Large Language Model (LLM) providers (OpenAI, Google Gemini, Anthropic Claude).

---

## 2. Business Goals (BRS §3.1.1)
- **BG-01 — Reduce Manual Reading Effort**: Eliminate tab-switching and fragmented copy-pasting for lookups, translations, and summaries.
- **BG-02 — Improve Content Comprehension**: Explain complex terminology, unpack dense passages, and translate in-context.
- **BG-03 — Knowledge Retention**: Reinforce learning through interactive comprehension checks (quizzes) and key takeaway extraction.
- **BG-04 — Reading Continuity**: Retain reading context, chat history, and highlights across sessions and multiple devices.
- **BG-05 — Personalization**: Adapt assistance style, explanation depth, and LLM provider choice to individual preferences.
- **BG-06 — Reading Accessibility**: Empower users with reading difficulties or dyslexia through typography customization (OpenDyslexic, bionic reading, line spacing) and AI text simplification.
- **BG-07 — Control, Transparency & Trust**: Ensure users retain full ownership of their data, understand AI limitations, receive grounded citations, and control sensitive data transmission.
- **BG-08 — Measurable Evaluation**: Provide clear telemetry and feedback mechanisms (helpful/unhelpful ratings, error diagnostics) to validate effectiveness.

---

## 3. Product Scope & 12 Core System Features (SRS §3.2)

The system encompasses 12 functional feature groups (Features A through L):

| Feature Code | Feature Name | Primary Purpose |
|---|---|---|
| **Feature A** | **Account & Session Management** (`FR-ACC-01~06`) | Registration, login, session validation, multi-account isolation on the same browser, and draft preservation upon session expiry. |
| **Feature B** | **Onboarding & User Configuration** (`FR-CFG-01~07`) | First-time setup wizard, default AI provider, per-request overrides, proactive assistance toggles, privacy mode toggles, and settings synchronization. |
| **Feature C** | **API Key Management (BYOK Vault)** (`FR-KEY-01~07`) | User-supplied API keys (max 1 active key per provider per account), pre-activation key validation, error isolation, envelope AES-256-GCM encrypted storage at rest, no plaintext logging. |
| **Feature D** | **Content Extraction & Reading Context** (`FR-CNT-01~08`) | Ingest web text, selected snippets, and PDFs. Strict **tab-isolated context** (no cross-tab context pollution). No auto-fetching of stale URLs upon opening historical chats. |
| **Feature E** | **AI Reading Assistance** (`FR-AI-01~12`) | Real-time SSE streaming for explain, translate, summarize, and multi-turn contextual Q&A. Strict source-grounding priority, uncertainty expression, and distinction between on-page facts vs external AI knowledge. |
| **Feature F** | **Comprehension Questions** (`FR-CMP-01~05`) | Dynamic generation of multiple-choice comprehension check quizzes after reading milestones; answer evaluation and feedback. |
| **Feature G** | **Proactive Reading Support & Personalization** (`FR-PRV-01~06`) | Non-intrusive proactive suggestions triggered by reading dwell time and complexity cues; customizable sensitivity or complete opt-out. |
| **Feature H** | **Privacy & Data Protection** (`FR-SEC-01~12`) | Pre-flight sensitive data inspection (PII, credentials, financial data) with default-block behavior, user override confirmation, domain blacklist policy, and privacy mode. |
| **Feature I** | **Conversation History & Data Lifecycle** (`FR-HIS-01~10`) | Granular history management: delete single conversation, clear all history, delete account. Strict multi-tenant isolation; distinction between data protection and history storage. |
| **Feature J** | **Synchronization & Conflict Handling** (`FR-SYN-01~08`) | Multi-device sync for conversations, settings, and highlights; versioned conflict detection without silent overwriting. Local caching during network drops. |
| **Feature K** | **Error Handling & Recovery** (`FR-ERR-01~10`) | Clear differentiation between key/quota errors, network failures, and upstream AI faults. Local preservation of unsent drafts; strict rule against silent automated re-submission. |
| **Feature L** | **Monitoring & Operational Support** (`FR-OPS-01~05`) | Health probes (`/health`), operational metrics, diagnostic logging without sensitive data or decrypted keys. |

### Extended Platform Scope: Web Management Portal (Admin & User)
- **User Dashboard (`/dashboard/*`)**: View cross-device reading stats, manage saved highlights, export reading notes, manage BYOK keys.
- **Admin Management Portal (`/admin/*`)**:
  - *User Management*: Paginated user list, account status moderation (Active / Suspended / Banned), role management (`user` / `admin`).
  - *System Telemetry & Health*: Live overview of total requests, upstream AI provider distribution (OpenAI vs Gemini vs Claude), error rates, and user feedback satisfaction score.
  - *Privacy Guarantee*: Admin has zero access to user decrypted API keys, reading text, or private conversation logs.

---

## 4. Key Target Users & Stakeholders (StRS §3.1)
- **General Readers & Learners**: Need rapid synthesis, plain-language summaries, vocabulary help, and comprehension quizzes.
- **Researchers & Knowledge Workers**: Need precise multi-turn Q&A, deep contextual synthesis, and grounded facts citing source evidence.
- **Users with Reading Difficulties / Dyslexia**: Need specialized typography (OpenDyslexic, bionic reading, adjusted line height) and AI text simplification.
- **Language Learners**: Need contextual translations explaining cultural nuance, grammar structures, and vocabulary idioms.

---

## 5. Non-Functional Attributes (SRS §3.3)
- **Security & Cryptography**: AES-256-GCM encryption for stored user API keys; salted bcrypt hashing for passwords; JWT token architecture; zero credentials in server logs.
- **Performance & Latency**: Real-time token streaming via Server-Sent Events (SSE) with async generator pipelines; non-blocking database queries via `asyncpg`.
- **Reliability & Data Preservation**: Unsent request drafts preserved locally upon network or provider failure; sync conflict detection preventing silent overwrites.
- **AI Groundedness & Honesty**: The system explicitly flags when a response relies on external LLM training data rather than the user's active page, and declares uncertainty when evidence is insufficient.
