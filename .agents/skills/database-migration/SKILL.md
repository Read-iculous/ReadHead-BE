---
name: database-migration
description: >-
  Use this skill when creating, applying, or managing Alembic database migrations
  in ReadHead-BE. Activate when the user asks to "add a column", "create a table",
  "run migration", "rollback migration", or any task involving database schema changes.
---

# Database Migration — ReadHead-BE (Alembic)

## Migration Principles
- **One schema change = one migration file** — do not bundle unrelated changes
- **Never edit a migration that has already been applied** to any environment
- **Always test downgrade** before merging to main
- Reference `.docs/database/schema.md` before creating any migration

## Alembic Setup (if not yet initialized)
```bash
alembic init alembic
# Edit alembic.ini: set sqlalchemy.url to your DB connection string
```

In `alembic/env.py`:
```python
from app.core.database import Base
from app.models import *  # Import all models so autogenerate can detect them

target_metadata = Base.metadata
```

## Creating a New Migration

### 1. Update the ORM Model first
Edit the file in `app/models/<resource>.py` — add, modify, or remove Columns.

### 2. Autogenerate the migration
```bash
alembic revision --autogenerate -m "descriptive_message"

# Good migration message examples:
# "add_users_table"
# "add_email_verified_column_to_users"
# "create_books_and_chapters_tables"
# "add_index_on_users_email"
```

### 3. Review the generated migration file
```
alembic/versions/<timestamp>_<slug>.py
```

**Always verify:**
- `upgrade()` is correct (adds the right columns/tables?)
- `downgrade()` correctly reverses the upgrade
- No missing dependency on a previous migration (`depends_on`)
- Autogenerate sometimes misses: check constraints, partial indexes, custom types

### 4. Apply the migration
```bash
# Apply all pending migrations
alembic upgrade head

# Apply one version at a time
alembic upgrade +1

# Apply to a specific revision
alembic upgrade <revision_id>
```

### 5. Verify
```bash
alembic current         # Check current version
alembic history --verbose  # View full history
```

### 6. Update docs
After the migration is applied:
- Update `.docs/database/schema.md` with the changes
- Update `.docs/database/relationships.md` if relationships changed
- Add an entry to `.docs/database/migrations.md`

## Rolling Back a Migration
```bash
alembic downgrade -1          # Rollback one version
alembic downgrade <revision>  # Rollback to a specific version
alembic downgrade base        # Rollback everything
```

## Troubleshooting

### "Target database is not up to date"
```bash
alembic upgrade head
```

### "Can't locate revision"
```bash
alembic history  # Inspect the migration chain
alembic stamp head  # Reset if DB is in an unknown state (use with caution!)
```

### Autogenerate detects no changes
- Check that `app/models/__init__.py` imports the new model
- Check that `alembic/env.py` imports the correct Base

### Migration conflict (two developers created migrations simultaneously)
```bash
alembic merge -m "merge_heads" <revision1> <revision2>
```
