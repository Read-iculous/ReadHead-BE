# Production Deployment Guide

> **Status**: No production deployment exists in the MVP, and no default admin account is created automatically (see `implementation-status.md`). This guide documents the intended production procedure derived from the local setup and existing tooling; it is not a claim that production hosting has been exercised.

## 1. Build & Run (Dockerfile + Runtime Environment)

The API is packaged using the repository root `Dockerfile`; environment configuration is supplied **at runtime**, never baked into the image, and database migrations run **separately** from the application container (same contract as local setup — see `setup.md`).

1. Build the image once per release tag:
   ```bash
   docker build -t readhead-be:<version> .
   ```
2. Supply configuration at runtime via environment variables (`DATABASE_URL`, `REDIS_URL`, `JWT_SECRET_KEY`, `ENCRYPTION_MASTER_KEYS`, `CURRENT_KEY_VERSION`, `RESEND_API_KEY`, `MAIL_FROM_ADDRESS`, `APP_BASE_URL`, ports — full registry in `.docs/technical/environment-variables.md`). Do not copy a `.env` file into the image; the local `.env` is git-ignored development material.
   - **Note (planned — BE-19)**: the email variables (`RESEND_API_KEY`, `MAIL_FROM_ADDRESS`, `APP_BASE_URL`, `VERIFICATION_TOKEN_TTL_HOURS`, `PASSWORD_RESET_TOKEN_TTL_MINUTES`, `VERIFICATION_RESEND_LIMIT_PER_HOUR`) are **not yet read by `config.py`** (`extra="ignore"`), so supplying them today is harmless but has no effect until BE-19 is implemented.
3. Run migrations as a separate, one-off step against the target database before (or while) the new version serves traffic:
   ```bash
   alembic upgrade head
   ```
4. Start the container:
   ```bash
   docker run -d --name readhead-be --env-file /secure/path/prod.env -p 8000:8000 readhead-be:<version>
   ```
   Multiple workers may run the same image; every worker must receive the **same** `ENCRYPTION_MASTER_KEYS` keyring (see the Zero-Downtime Rotation Runbook in `commands.md`).
5. Bootstrap the initial administrator via CLI, once, with server-level access (ADR-019 — there is deliberately no role-promotion API):
   ```bash
   python -m app.cli.create_admin --email admin@readhead.io --password "SecureAdminPassword123!"
   ```

## 2. Secrets Management

- All secrets live in environment variables provided by the deployment platform's secret store (or an equivalent runtime `--env-file` with restrictive permissions). **No secret is ever committed** to the repository; the committed `.env.example` contains placeholders only.
- `ENCRYPTION_MASTER_KEYS` is the highest-value secret: it decrypts every stored BYOK key. Distribute it only to API workers and maintenance processes, rotate exclusively via the Zero-Downtime Rotation Runbook in `commands.md`, and pair every backup with the key versions it needs (Backup & Restore Runbook, `commands.md`).
- Database/Redis credentials, the JWT secret and `RESEND_API_KEY` follow the same rule: injected at runtime, never logged (`FR-OPS-03`), never echoed in error responses or issue reports. (`RESEND_API_KEY` is planned — BE-19; see §1 for the not-yet-implemented email variables.)
- If a secret is suspected to be leaked, rotate it (keys via the rotation runbook; DB/Redis credentials via the provider) and revoke user sessions where the exposure implies account access.

## 3. Rollback Deployment

1. Keep the previous release image (`readhead-be:<previous>`) available on the host until the new version has passed the health checks in §4.
2. Schema migrations are **forward-only in practice**: a rollback redeploys the previous image, but the database usually stays at the new revision. This is safe for all current additive migrations (`0004`–`0008` are new tables/columns/indexes the old code simply ignores); a genuinely destructive migration (e.g. `0007` column drop) must not be rolled back after it is applied — restore from backup instead (Backup & Restore Runbook).
3. Roll back the container:
   ```bash
   docker stop readhead-be && docker rm readhead-be
   docker run -d --name readhead-be --env-file /secure/path/prod.env -p 8000:8000 readhead-be:<previous>
   ```
4. Confirm the rolled-back workers can still read the current schema (`alembic current` unchanged) and that health checks pass (§4). Never remove an encryption key version still referenced by stored records, even after rollback.

## 4. Post-Deploy Health Checks

- **Readiness**: `GET /api/v1/health` (§1.1) must return `200 OK` with `status: "healthy"` — PostgreSQL is mandatory; `status: "degraded"` (Redis down) means the instance may serve but investigate before proceeding.
- **Liveness**: `GET /api/v1/health/live` (§1.2) returns for each running container; the orchestrator (or process supervisor) should restart instances on failure.
- **Functional smoke**: one authenticated request against a non-AI endpoint (e.g. `GET /users/me`) and, where credentials allow, `GET /admin/telemetry` with an admin account.
- **Migration check**: `alembic current` on the production database equals the expected head revision for the deployed release.
- Monitoring scope in the MVP is deliberately limited to these health probes plus admin telemetry (§9.1): APM agents, Prometheus exporters and alerting pipelines are out of scope (SYS-FUN-062; OpsCon out-of-scope).

## 5. Zero-Downtime Notes

- Rolling deploys rely on the shared PostgreSQL/Redis state, so workers of the old and new version may run concurrently only when both tolerate the same schema — keep additive migrations separate from code that uses them (deploy schema first, code second).
- Encryption key changes are **not** a deploy event: they follow the Zero-Downtime Rotation Runbook in `commands.md` (dual keyring → writer switch → batch re-encryption → verification), independent of image releases.
- For data-level rollback and host loss, use the Backup & Restore Runbook in `commands.md` (RTO/RPO targets are placeholders pending approval).
