---
name: code-review
description: >-
  Use this skill when reviewing code changes in ReadHead-BE for correctness,
  style, security, and architecture compliance. Activate when the user asks
  to "review this code", "check this PR", "is this implementation correct?",
  or when the agent finishes implementing something and wants to self-review.
---

# Code Review — ReadHead-BE

## Review Process

### Step 1: Understand the Context
- What was the task being implemented?
- Which files were changed?
- Were any migrations created?

### Step 2: Architecture Review
Check against `03-architecture-compliance.md`:

```
[ ] Router only delegates — no business logic
[ ] Business logic is correctly placed in the service layer
[ ] Model only defines structure — no logic
[ ] Import direction is correct (no circular imports, no reverse imports)
[ ] Each layer only calls the layer directly below it
```

### Step 3: Coding Standards Review
Check against `04-coding-standards.md`:

```
[ ] Type hints present on all functions
[ ] Naming conventions correct (snake_case functions, PascalCase classes)
[ ] Pydantic models use correct suffixes (Create / Update / Response)
[ ] Response format is correct ({data: ..., total: ..., page: ...})
[ ] Error format is correct ({detail: ..., code: ...})
[ ] HTTP status codes are correct (201 for create, 204 for delete, etc.)
[ ] No print() or debug code
[ ] No hardcoded strings, URLs, or secrets
```

### Step 4: FastAPI Conventions Review
Check against `07-python-fastapi-conventions.md`:

```
[ ] All DB operations are async/await
[ ] Depends() used correctly for database and auth
[ ] Pagination includes: page, page_size, total, total_pages
[ ] Settings read from config — not hardcoded
[ ] Import order correct (stdlib → third-party → local)
```

### Step 5: Security Review
```
[ ] Authentication enforced on the correct endpoints
[ ] No sensitive data exposed in responses (password hashes, secret keys)
[ ] SQL injection not possible (ORM used — no raw string SQL)
[ ] Input validation complete in Pydantic schemas
[ ] Pagination in place to prevent full table dumps
[ ] Error messages do not leak sensitive information
```

### Step 6: Test Review
```
[ ] Happy path is tested
[ ] Error cases tested (404, 422, 401, 409)
[ ] Test names are clear: test_<function>_<scenario>_<expected>
[ ] Tests are independent (no test depends on another)
[ ] Fixtures used correctly — no hardcoded data inside tests
```

### Step 7: Documentation Review
```
[ ] .docs/api/endpoints.md updated (if new endpoints were added)
[ ] .docs/database/schema.md updated (if a migration was applied)
[ ] Docstrings present on public functions
[ ] Complex logic has explanatory comments
```

## Red Flags — Stop and ask the user if any of these are found:
- ❌ Business logic inside a router
- ❌ Direct DB calls inside a router
- ❌ Credentials or secrets in code
- ❌ Unpaginated query that could load entire tables
- ❌ Exception silently caught and ignored
- ❌ Blocking I/O inside an async function (`time.sleep`, `requests.get`)
- ❌ Editing a migration that has already been applied
- ❌ Circular imports

## Review Output Format
```
## Code Review Summary

### ✅ Looks Good
- [list positives]

### ⚠️ Suggestions (non-blocking)
- [items to improve but not critical]

### ❌ Must Fix (blocking)
- [errors that must be fixed before accepting]

### Security Concerns
- [if any]
```
