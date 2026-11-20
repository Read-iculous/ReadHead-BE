# 06 — Documentation Maintenance

## Principle: Docs Are Code
Documentation in `.docs/` must be treated as a **first-class artifact**, not an afterthought.
When code changes but docs are not updated → docs become a hazard (the agent reads wrong information).

## When to Update Docs

| Action | Docs file to update |
|---|---|
| Add / modify / remove an endpoint | `.docs/api/endpoints.md` |
| Add / modify / remove a DB table | `.docs/database/schema.md` |
| Change relationships between tables | `.docs/database/relationships.md` |
| Create a new migration | `.docs/database/migrations.md` |
| Add a new environment variable | `.docs/technical/environment-variables.md` |
| Add a dependency to `requirements.txt` | `.docs/technical/dependencies.md` |
| Change auth flow | `.docs/technical/auth-flow.md` |
| Discover an important bug or quirk | `.docs/knowledge/known-issues.md` |
| Make a significant technical decision | `.docs/knowledge/decisions.md` |
| Change architecture | `.docs/architecture/overview.md` |

## Documentation Format Standards

### Endpoint entry
```markdown
## POST /api/v1/users
- **Description**: Create a new user
- **Auth**: Not required
- **Request body**: `UserCreate`
- **Response**: `201 UserResponse`
- **Errors**: `409 EMAIL_ALREADY_EXISTS`
```

### Schema table entry
```markdown
## Table: users
| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| id | BIGINT | NO | auto | Primary key |
| email | VARCHAR(255) | NO | - | Login email |
```

### Known issue entry
```markdown
## [ISSUE-001] Short Issue Name
- **Discovered**: YYYY-MM-DD
- **Severity**: Low / Medium / High
- **Description**: ...
- **Workaround**: ...
- **Fix plan**: ...
```

## Documentation Rules
- ❌ No real credentials or secrets in docs
- ❌ No "planned" features documented as if already implemented — mark clearly as `[PLANNED]`
- ❌ No references to files or functions that no longer exist

## Docs Review Process
Before closing any task that changes architecture or API:
1. Open the relevant docs file
2. Update the information
3. Verify no stale or incorrect content remains
4. Inform the user that docs have been updated
