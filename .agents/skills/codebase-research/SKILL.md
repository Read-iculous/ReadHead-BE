---
name: codebase-research
description: >-
  Use this skill when searching for existing code, patterns, or implementations
  within ReadHead-BE before writing new code. Activate when the user asks
  "find where X is implemented", "how is Y handled currently?", or when
  the agent needs to locate relevant code before implementing a new feature.
---

# Codebase Research — ReadHead-BE

## Goal
Precisely locate relevant code before implementing anything, to avoid duplication and ensure consistency.

## Step 1: Extract search keywords
From the requirement, identify:
- Resource name (e.g. `user`, `book`, `chapter`)
- Action name (e.g. `create`, `authenticate`, `upload`)
- Field or column name (e.g. `email`, `isbn`, `content`)

## Step 2: Search the codebase
```bash
# Search by keyword across all Python files
grep -r "keyword" app/ --include="*.py" -l

# Find function or class definitions
grep -rn "def keyword\|class keyword" app/ --include="*.py"

# Search in test files
grep -r "keyword" tests/ --include="*.py" -l

# Find usages of an import
grep -rn "from app.models.user import\|import user" app/
```

## Step 3: Read the relevant files
Once files are identified:
1. Read the full file to understand context
2. Pay attention to imports, dependencies, and patterns used
3. Read the corresponding tests to understand expected behavior

## Step 4: Find a similar pattern to follow
```bash
# Find an already-implemented resource to use as reference
# Example: implementing 'book' — look at how 'user' was done
Get-ChildItem app/routers/ -Filter "*.py"
Get-ChildItem app/services/ -Filter "*.py"
```

## Step 5: Report findings
Present:
- Where related code was found (file, line)
- Which patterns are currently used
- What can be reused
- Potential conflicts or dependencies to be aware of

## Search Tips
- Search by schema name rather than table name
- Search both singular and plural forms
- Check `conftest.py` for relevant existing fixtures
- Check `app/core/exceptions.py` for existing error types
