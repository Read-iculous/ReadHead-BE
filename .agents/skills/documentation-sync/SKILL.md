---
name: documentation-sync
description: >-
  Use this skill when synchronizing .docs/ files after code changes in ReadHead-BE.
  Activate when the agent has finished implementing a feature or migration and
  needs to update documentation, or when the user asks "update the docs",
  "sync documentation", or "docs are out of date".
---

# Documentation Sync — ReadHead-BE

## Goal
Ensure `.docs/` always accurately reflects the current state of the codebase.
Stale docs are more harmful than no docs.

## When to Run This Skill
- After implementing a new endpoint
- After creating / applying a migration
- After changing the architecture
- After adding a new environment variable
- After discovering an important bug
- Periodically as a routine check (monthly doc review)

## Step 1: Identify the Scope of Changes
List everything that changed in this session:
- New / modified / removed endpoints?
- DB schema changes?
- Auth flow changes?
- New env vars?
- New dependencies?

## Step 2: Update Each Relevant File

### Endpoint change → `.docs/api/endpoints.md`
Standard format:
```markdown
## [METHOD] /api/v1/<path>
- **Description**: <short description>
- **Auth**: Required / Not required / Admin only
- **Request body**: `<SchemaName>` (if applicable)
- **Query params**: `page`, `page_size` (if applicable)
- **Response**: `<status> <SchemaName>`
- **Errors**: `<status> <ERROR_CODE>`, ...
- **Implemented in**: `app/routers/<file>.py`
```

### DB schema change → `.docs/database/schema.md`
Standard format:
```markdown
## Table: <table_name>
| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| id | BIGINT | NO | auto | Primary key |
```

### New migration → `.docs/database/migrations.md`
```markdown
## <YYYY-MM-DD> — <migration name>
- **File**: `alembic/versions/<hash>_<slug>.py`
- **Change**: <description>
- **Reason**: <why this change was needed>
```

### New env var → `.docs/technical/environment-variables.md`
```markdown
| Variable name | Required | Default | Description |
|---------------|----------|---------|-------------|
| NEW_VAR | Yes/No | <default> | <description> |
```

### New issue discovered → `.docs/knowledge/known-issues.md`
```markdown
## [ISSUE-XXX] <short name>
- **Discovered**: YYYY-MM-DD
- **Severity**: Low / Medium / High
- **Description**: ...
- **Workaround**: ...
- **Fix plan**: ...
```

## Step 3: Consistency Check
```
[ ] Endpoint names in docs match the actual code routes
[ ] Schema columns in docs match the ORM models
[ ] Error codes in docs exist in app/core/exceptions.py
[ ] Env var names in docs match app/core/config.py
[ ] File paths in docs point to files that actually exist
```

## Step 4: Report to User
List:
- Files that were updated
- Key content changes made
- Any discrepancies or issues found during the sync
