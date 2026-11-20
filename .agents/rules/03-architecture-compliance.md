# 03 — Architecture Compliance

## Overall Architecture
ReadHead-BE follows a **Layered Architecture**:

```
HTTP Request
     ↓
┌──────────────┐
│   Router     │  ← Receives request, validates input, returns response
│  (routers/)  │  ← NO business logic here
└──────┬───────┘
       ↓
┌──────────────┐
│   Service    │  ← All business logic lives here
│  (services/) │  ← Calls DB through models
└──────┬───────┘
       ↓
┌──────────────┐
│    Model     │  ← ORM model, maps to DB table
│   (models/)  │  ← Defines structure only, no logic
└──────┬───────┘
       ↓
  PostgreSQL DB
```

## Rules Per Layer

### Router layer (`app/routers/`)
- ✅ Receive HTTP requests, parse path/query params
- ✅ Call service functions
- ✅ Return HTTP responses with correct status codes
- ❌ No business logic (no business-rule if/else)
- ❌ No direct DB / ORM queries
- ❌ No complex data transformations

### Service layer (`app/services/`)
- ✅ Contains all business logic
- ✅ Calls models to query the DB
- ✅ Raises exceptions with clear error codes
- ✅ Handles DB transactions when needed
- ❌ Does not import from `routers/`
- ❌ Does not return HTTP Response objects

### Schema layer (`app/schemas/`)
- ✅ Pydantic models for request validation and response serialization
- ✅ Each resource has: `Create`, `Update`, `Response`, `ListResponse`
- ❌ No business logic
- ❌ No DB calls

### Model layer (`app/models/`)
- ✅ ORM models mapping to database tables
- ✅ Defines relationships between tables
- ❌ No business logic
- ❌ No complex methods

### Core layer (`app/core/`)
- `config.py` — Settings from environment variables
- `auth.py` — JWT decode/encode, auth dependency injection
- `database.py` — DB session management
- `exceptions.py` — Custom exception classes

## Import Direction Rules
```
routers → services → models
routers → schemas
services → schemas (when needed)
core → (imported by all layers)
```
No reverse or circular imports are allowed.

## See Also
- Component details: `.docs/architecture/components.md`
- Architecture decisions: `.docs/architecture/decisions.md`
