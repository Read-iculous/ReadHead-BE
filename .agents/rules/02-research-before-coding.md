# 02 — Research Before Coding

## Mandatory process before implementing anything

### Step 1: Define the task scope
Read the requirement carefully and answer:
- Which layers does this task affect? (router / schema / service / model / config)
- Which DB tables are involved?
- Which endpoints are involved?

### Step 2: Read relevant documentation
Based on the scope, read the corresponding `.docs/` files:

| If the task involves... | Read this file |
|---|---|
| Database / Schema | `.docs/database/schema.md`, `.docs/database/relationships.md` |
| New API / Endpoint | `.docs/api/endpoints.md`, `.docs/api/error-codes.md` |
| Authentication | `.docs/technical/auth-flow.md` |
| Business logic | `.docs/project-overview.md`, `.docs/architecture/components.md` |
| Configuration | `.docs/technical/environment-variables.md` |
| Known bugs | `.docs/knowledge/known-issues.md` |

### Step 3: Survey existing code (if any)
When code already exists, before adding anything new:
1. Find related files: `grep -r "keyword" app/`
2. Read the interface of existing services/models
3. Check if any tests already cover it: `ls tests/`

### Step 4: Identify the pattern to follow
- Find 1–2 similar examples already implemented in the codebase
- Follow that exact pattern — do not invent a new style

### Step 5: Plan before coding
Before writing code, present:
- Which files will be created / modified
- What the main logic is
- Edge cases to handle

## Research Checklist (paste before each major task)
```
[ ] Read relevant docs in .docs/
[ ] Found similar code in codebase (if any exists)
[ ] Understand the related DB schema
[ ] Identified which files to create/modify
[ ] Presented the plan to the user
```
