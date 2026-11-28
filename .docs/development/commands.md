# Development Commands Reference

## 1. Server Execution
```bash
# Start server with hot reload (dev mode)
uvicorn app.main:app --reload --port 8000

# Start server with verbose logging
uvicorn app.main:app --reload --log-level debug

# Production start with multiple workers
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

## 2. Database & Migrations (Alembic)
```bash
# Generate a new migration revision based on model changes
alembic revision --autogenerate -m "descriptive_name"

# Apply all pending migrations to the latest revision
alembic upgrade head

# Rollback the last migration
alembic downgrade -1

# Show current database revision
alembic current

# Show migration history
alembic history --verbose
```

## 3. Testing (Pytest)
```bash
# Run all tests
pytest

# Run tests with verbose output and print statements
pytest -v -s

# Run tests with test coverage report
pytest --cov=app --cov-report=term-missing --cov-report=html

# Run unit tests only
pytest tests/unit/

# Run integration tests only
pytest tests/integration/

# Run the auth-focused integration files (there is no test_auth_api.py)
pytest tests/integration/test_ai_quiz_oauth_admin.py tests/integration/test_account_cache_url_refresh_errors.py tests/integration/test_concurrency_privacy_review.py tests/integration/test_send_disconnect_domain_password.py -v
```

## 4. Code Quality, Formatting & Linting
```bash
# Format code with Black
black app/ tests/

# Sort imports with isort
isort app/ tests/

# Check formatting without modifying files
black --check app/ tests/
isort --check-only app/ tests/

# Run Ruff linter
ruff check app/ tests/

# Run static type checking with Mypy
mypy app/
```

## 5. Security & Maintenance Utilities
```bash
# Bootstrap the initial Super Admin account
python -m app.cli.create_admin --email admin@readhead.io --password "SecureAdminPassword123!"

# Rotate master encryption key for stored BYOK user keys (upgrades v1 -> v2)
python -m app.cli.rotate_keys --old-version v1 --new-version v2

# Purge soft-deleted tombstones older than 30 days (cascades to messages & feedback)
python -m app.cli.purge_tombstones --days 30
```

## 6. Docker & Infrastructure Services
```bash
# Start PostgreSQL 15 and Redis 7 in the background
docker compose up -d

# Check status and health of backend services
docker compose ps

# View logs from running containers
docker compose logs -f

# Stop services preserving database volumes
docker compose down

# Stop services and remove volumes (clean reset)
docker compose down -v
```

### Zero-Downtime Rotation Runbook
1. Distribute `ENCRYPTION_MASTER_KEYS` containing both `v1` and `v2` to every API worker and maintenance process. Keep `CURRENT_KEY_VERSION=v1` until every process can decrypt both versions.
2. Roll out `CURRENT_KEY_VERSION=v2` to **all writers** and confirm no old-version writer remains. Keep both keys available; existing `v1` records remain readable.
3. Run `python -m app.cli.rotate_keys --old-version v1 --new-version v2`. Process bounded batches. Each update uses a compare-and-swap on record ID and the exact original ciphertext (`WHERE id = :id AND encrypted_key = :original_ciphertext`), so a concurrent user key replacement is never overwritten. Skip/re-read changed rows; resume safely after interruption. Cipher-only re-encryption does not change user-visible metadata.
4. Verify every active writer still uses `v2`, no database row has a `v1:` prefix, and a second scan finds zero remaining `v1` rows. Only then remove `v1` from live keyrings. Retain old key material securely for the backup-restore retention policy; restoring an old backup requires its matching key.
5. On migration failure keep the dual keyring and continue serving reads/writes with `v2`; resume migration. Never remove a key still referenced by a record. Rolling back a writer to `v1` invalidates the completion check and requires another migration scan.

### Resend Email Runbook (BE-19)

**Domain setup (SPF / DKIM / DMARC)**
1. Register a Resend account, add the sending domain (e.g. `readhead.io`) under Domains, and publish the DNS records Resend displays:
   - **SPF**: `v=spf1 include:amazonses.com ~all` (Resend sends via Amazon SES) as a TXT record on the apex.
   - **DKIM**: the three `resend._domainkey` CNAME records shown by Resend (selectors differ per domain).
   - **DMARC**: TXT `_dmarc.readhead.io` starting at `v=DMARC1; p=none; rua=mailto:dmarc@readhead.io`, tightening to `p=quarantine`/`p=reject` once reports look clean.
2. Wait for the domain to show **Verified** in Resend before sending from production (`MAIL_FROM_ADDRESS` must use that domain; e.g. `no-reply@readhead.io`).
3. Set `RESEND_API_KEY`, `MAIL_FROM_ADDRESS` and `APP_BASE_URL` in `.env` (see `.docs/technical/environment-variables.md`).

**Testing email locally**
```bash
# 1. Register a local test account (uses APP_BASE_URL for link building)
curl -i -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "SecurePassword123!", "full_name": "Test User"}'

# 2. Login must be blocked before verification
curl -i -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "SecurePassword123!"}'
# -> 403 EMAIL_NOT_VERIFIED

# 3. Resend the verification email (rate limit: 3/hour per address)
curl -i -X POST http://localhost:8000/api/v1/auth/verify-email/resend \
  -H "Content-Type: application/json" -d '{"email": "test@example.com"}'

# 4. Read the token from the Resend dashboard/test inbox (or the local catcher below),
#    then verify and log in
curl -i -X POST http://localhost:8000/api/v1/auth/verify-email -H "Content-Type: application/json" -d '{"token": "<token_from_email>"}'
curl -i -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" -d '{"email": "test@example.com", "password": "SecurePassword123!"}'
```
- Without a paid domain, point `APP_BASE_URL` at `http://localhost:8000` and set `MAIL_FROM_ADDRESS=noreply@resend.dev` (Resend's shared test sender). Caveat: `@resend.dev` addresses are deliverable **only to the email account of the Resend account that owns the API key** — no other recipient will receive mail, and the API key must remain in `.env` only. Production still requires a verified custom domain per the Domain setup steps above.
- To catch mail fully offline (no Resend calls), run a local SMTP catcher such as `python -m smtpd -c DebuggingServer -n localhost:1025` or MailHog (`docker run -p 8025:8025 mailhog/mailhog`) and stub the email service transport in tests instead of the real API.

**Bounce / spam-folder handling**
- Registration/login issues where mail never arrives: check the Resend dashboard Emails tab for the send's status (`delivered`, `bounced`, `complained`). Bounces list the SMTP diagnostic; common causes are an unverified domain, missing SPF/DKIM records, or a recipient-side block.
- If mail lands in spam: verify DKIM/DMARC alignment for the sending domain, warm the domain gradually (keep early volume low), and avoid spammy link-only bodies. Verification/reset links must point at the real `APP_BASE_URL` (mismatched or localhost links in production look phishing-like).
- Mail failures must never fail registration (`verification_email_sent: false` + sanitized log); after fixing DNS/API-key issues, have the user re-request via `POST /auth/verify-email/resend` (3/hour cap) rather than re-registering.
- Never paste tokens, links or mail payloads into logs or issue reports (`FR-OPS-03`).
