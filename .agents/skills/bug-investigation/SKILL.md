---
name: bug-investigation
description: >-
  Use this skill when investigating a bug, error, or unexpected behavior in
  ReadHead-BE. Activate when the user reports "this endpoint returns wrong data",
  "getting 500 error", "X doesn't work", or provides an error traceback.
---

# Bug Investigation — ReadHead-BE

## Standard Debug Process

### Step 1: Gather Information
Before doing anything, collect:
- Full error message / traceback
- The failing endpoint (method + path)
- Request data sent (body, headers, params)
- What was the expected behavior?
- What actually happened?
- When does the error occur? (always / sometimes / under what condition?)

### Step 2: Read the Traceback
```
Traceback (most recent call last):
  File "...", line X, in <module>    ← Entry point
  ...
  File "app/services/user_service.py", line 45, in create_user  ← Relevant file
    ...
<ErrorType>: <error message>         ← Root cause
```

From the traceback, determine:
- Which layer is failing? (router / service / model / core)
- Which exact file and line?

### Step 3: Read the Relevant Code
Read the failing file, focusing on the line indicated in the traceback.
Read the surrounding context (10 lines before and after).

### Step 4: Check Common Root Causes

#### 500 Internal Server Error
- Unhandled exception in a service?
- Missing None check?
- Incorrect DB query?
- Circular import?

#### 422 Unprocessable Entity
- Pydantic validation failure?
- Missing required fields?
- Wrong data types?

#### 404 Not Found
- Is the route correct? (prefix? trailing slash?)
- Does the resource ID actually exist in the DB?

#### 401 / 403
- Expired token?
- Malformed token?
- Does the user have the correct permissions?

#### Wrong data returned
- Bug in service logic?
- Pydantic schema missing a field?
- DB query returning wrong records?

### Step 5: Reproduce Locally
```python
# Write a minimal test case to reproduce the bug
async def test_reproduce_bug():
    # Set up the exact conditions that trigger the bug
    response = await client.<method>("<endpoint>", ...)
    print(response.json())  # Debug only — remove after
```

### Step 6: Check Known Issues
Read `.docs/knowledge/known-issues.md` — this bug may already be documented.

### Step 7: Fix and Verify
After applying the fix:
1. The reproducing test case must pass
2. All related existing tests must still pass
3. Run `pytest tests/ -v`

### Step 8: Document
If the bug stems from a non-obvious quirk or edge case:
- Add an entry to `.docs/knowledge/known-issues.md`
- Add a comment in the code at the fix location

## Useful Debug Commands
```bash
# Run the server with hot reload and verbose logging
uvicorn app.main:app --reload --log-level debug

# Run tests with full output
pytest tests/ -v -s --tb=long

# Check DB directly (psql)
# SELECT * FROM users WHERE id = 1;
```

## Common Python / FastAPI Gotchas
- **Async in sync context**: Calling `async def` without `await` returns a coroutine object that is never executed
- **SQLAlchemy lazy loading**: Accessing a relationship outside a session context → `DetachedInstanceError`
- **Pydantic v2 breaking changes**: `dict()` → `model_dump()`, `orm_mode` → `from_attributes`
- **Alembic detects no changes**: Model not imported in `env.py`
