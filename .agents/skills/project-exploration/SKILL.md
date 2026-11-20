---
name: project-exploration
description: >-
  Use this skill when first entering the ReadHead-BE project or when the agent
  needs to build an initial mental model of the codebase. Activate when the user
  asks "how is the project structured?", "what does this project do?", or when
  starting a new session without prior context.
---

# Project Exploration — ReadHead-BE

## Goal
Build a complete mental model of the project before starting any task.

## Step 1: Read the overview docs (in order)
1. `AGENTS.md` at root — fastest context
2. `.docs/project-overview.md` — project goals and scope
3. `.docs/system-context.md` — position in the larger system
4. `.docs/architecture/overview.md` — overall architecture

## Step 2: Understand the tech stack
1. `.docs/technical/tech-stack.md` — framework, database, tools
2. `.docs/technical/dependencies.md` — libraries in use
3. `requirements.txt` or `pyproject.toml` — specific versions

## Step 3: Survey the directory structure (once code exists)
```bash
# Get a top-level overview
Get-ChildItem -Recurse -Depth 3 | Where-Object { !$_.FullName.Contains("__pycache__") }

# List existing routers
Get-ChildItem app/routers/

# List existing models
Get-ChildItem app/models/
```

## Step 4: Understand the database
1. `.docs/database/schema.md` — all tables and columns
2. `.docs/database/relationships.md` — relationships between tables
3. `alembic/versions/` — migration history (if any)

## Step 5: Understand the API surface
1. `.docs/api/endpoints.md` — full list of all endpoints
2. `.docs/api/error-codes.md` — standardized error codes

## Step 6: Summarize for the user
After the survey, present:
- What the project does (1–2 sentences)
- Stack: framework, DB, auth method
- Number of main resources/entities
- Any notable points (constraints, known issues)
