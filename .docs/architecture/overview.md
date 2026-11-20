# Architecture Overview

## 1. Architectural Style
ReadHead-BE is built using a **Modular Layered Architecture** with an **Asynchronous I/O Pipeline**. The design guarantees strict separation of concerns, high throughput for concurrent streaming connections, and testability.

```
                           [ Incoming HTTP / SSE Request ]
                                          |
                                          v
+-----------------------------------------------------------------------------------+
| 1. API Routing Layer (`app/routers/`)                                             |
|    - Validates parameters & request bodies via Pydantic Schemas.                  |
|    - Authenticates & Authorizes requests via `Depends(get_current_user)`.         |
|    - Manages HTTP status codes, headers, and SSE streaming responses.             |
+-----------------------------------------+-----------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
| 2. Business Logic / Service Layer (`app/services/`)                              |
|    - Enforces business rules and privacy validations (e.g. domain blacklist).     |
|    - Coordinates transactions and entity lifecycles.                              |
|    - Delegates AI generation to the Unified LLM Gateway.                          |
+-------------------+-------------------------------------+-------------------------+
                    |                                     |
                    v                                     v
+---------------------------------------+ +-----------------------------------------+
| 3. Data Access Layer (`app/models/`)  | | 4. Unified LLM Gateway (`app/core/ai/`) |
|    - SQLAlchemy Async ORM models.     | |    - Provider Factory & Interfaces.     |
|    - Encrypted field transforms.      | |    - Adapters: OpenAI, Gemini, Claude.  |
|    - PostgreSQL persistence.          | |    - Async generators for SSE stream.   |
+---------------------------------------+ +-----------------------------------------+
```

## 2. Architectural Principles
1. **Thin Routers, Rich Services**: Routers do not perform queries, encrypt keys, or construct prompts. They only translate HTTP into service calls and service results into HTTP responses.
2. **Provider Agnostic Core**: Core business logic interacts exclusively with an abstract `BaseAIProvider` protocol, never directly with specific SDKs.
3. **Zero Plaintext Key Storage**: User API keys are symmetrically encrypted at rest via AES-256-GCM using an environment-level master secret. Plaintext keys only exist ephemerally in worker memory during upstream LLM calls.
4. **Non-blocking Streaming**: All LLM interactions yield chunks asynchronously using Python's `AsyncGenerator[str, None]` to prevent thread exhaustion during long streaming responses.
5. **Strict Boundary Validation**: Inbound payloads are strictly validated using Pydantic V2 schemas before touching any internal service.
