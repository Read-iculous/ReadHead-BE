---
name: feature-implementation
description: >-
  Use this skill when implementing a complete feature end-to-end in ReadHead-BE,
  spanning multiple components (database, API, business logic). Activate when the
  user describes a feature like "implement user registration", "add book search",
  or "build reading history tracking" — tasks larger than a single endpoint.
---

# Feature Implementation — ReadHead-BE

## What Counts as a "Feature"
A feature is a complete, user-facing capability.
Examples: "User Registration", "Book Search", "Reading Progress Tracking".

## Step 1: Feature Analysis
Analyze the requirement and answer:
1. Which DB tables are affected?
2. Which endpoints are needed? (full CRUD or just some?)
3. Is authentication required? What permissions?
4. Any special business rules? (validation, side effects, notifications?)
5. Are any existing services reusable?

## Step 2: Read Relevant Docs
- `.docs/database/schema.md` — related schema
- `.docs/api/endpoints.md` — existing endpoints
- `.docs/project-overview.md` — business context
- `.docs/knowledge/constraints.md` — constraints to be aware of

## Step 3: Plan and Present to User
Before writing code, present:
```
Feature: <feature name>

DB Changes:
- [ ] Migration: <description>

Files to create/modify:
- [ ] app/models/<resource>.py
- [ ] app/schemas/<resource>.py
- [ ] app/services/<resource>_service.py
- [ ] app/routers/<resource>s.py

Endpoints:
- [ ] POST /api/v1/<resource>s
- [ ] GET /api/v1/<resource>s/{id}

Tests:
- [ ] tests/integration/test_<resource>s.py

Docs to update:
- [ ] .docs/api/endpoints.md
- [ ] .docs/database/schema.md (if migration needed)
```

## Step 4: Implement in Order
```
1. Migration (if needed) → see skill: database-migration
2. ORM Model
3. Pydantic Schemas
4. Service layer
5. Router
6. Register router in app/routers/router.py
7. Tests
8. Update docs
```

## Step 5: Integration Test the Full Flow
Write a test simulating the complete user journey:
```python
# Example: "User Registration + Login" feature
async def test_user_registration_flow(client):
    # 1. Register
    response = await client.post("/api/v1/auth/register", json={...})
    assert response.status_code == 201

    # 2. Login
    response = await client.post("/api/v1/auth/login", json={...})
    token = response.json()["data"]["access_token"]

    # 3. Use the token to call a protected endpoint
    headers = {"Authorization": f"Bearer {token}"}
    response = await client.get("/api/v1/users/me", headers=headers)
    assert response.status_code == 200
```

## Step 6: Final Review Checklist
```
[ ] All tests pass: pytest -v
[ ] Code is formatted: black --check app/
[ ] Type hints are complete
[ ] Docs have been updated
[ ] No print() or debug code remaining
[ ] No hardcoded values
[ ] Edge cases are handled and tested
```
