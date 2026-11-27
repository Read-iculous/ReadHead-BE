# ReadHead-BE

Async FastAPI backend for the Intelligent Reading Assistant Chrome extension. Provides session-based JWT/OAuth login, AES-256-GCM BYOK storage, reading data, source-grounded AI streaming, comprehension quizzes, cross-device sync and administrator APIs.

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
```

Set generated `JWT_SECRET_KEY` and `ENCRYPTION_MASTER_KEY` in `.env` (generation commands are in the template). Then:

```bash
docker compose up -d
alembic upgrade head
uvicorn app.main:app --reload --port 8000 --no-access-log
```

- Swagger: <http://localhost:8000/docs>
- Readiness: <http://localhost:8000/api/v1/health>
- Liveness: <http://localhost:8000/api/v1/health/live>

If ports are occupied, set `POSTGRES_PORT` / `REDIS_PORT` and change the ports in `DATABASE_URL` / `REDIS_URL` to match. Docker Compose starts only this project's PostgreSQL and Redis. The API runs separately.

Register, log in, and use the returned access token with Swagger's **Authorize** button. Add your own provider key through `/api/v1/api-keys` before using AI. Google/GitHub login requires the corresponding OAuth environment configuration. Provider/model availability is controlled by the upstream account; model IDs in the specification are initial defaults and may require updating in user settings.

## Operations

```bash
python -m app.cli.create_admin --email admin@example.com
python -m app.cli.rotate_keys --old-version v1 --new-version v2
python -m app.cli.purge_tombstones --days 30
```

Read the keyring rollout procedure in [.docs/development/commands.md](.docs/development/commands.md) before rotating keys. Schema is changed only by Alembic, never by application startup.

A `Dockerfile` is included for the API. Provide environment variables at runtime; container builds exclude `.env` and the API image does not start or migrate databases automatically.

## Implementation and verification

The backend implementation covers BE-01–BE-16 and BE-18. Focused review regressions run with `python -m pytest tests/ -q`; a Redis integration check is opt-in. The full BE-17 integration/error suite and coverage targets remain incomplete. Real provider calls and OAuth require configured accounts and were not exercised.

To run all current automated tests against disposable PostgreSQL/Redis containers:

```bash
python tests/run_integration.py --report-dir /tmp/readhead-integration-report
```

The runner applies the existing migrations, executes the suite, saves pytest/JUnit/coverage reports, and stops only its own containers. AI/OAuth upstream HTTP responses are synthetic fixtures; the installed SDKs, authentication, business services and database/cache operations are real. Normal `pytest` skips these database tests unless explicitly enabled with disposable storage configuration. This verifies local behavior and error handling; successful real AI calls and OAuth consent/login still require live test credentials.

For an opt-in browser/database check, install `playwright` in the development environment and start the current source with `uvicorn app.main:app --host 127.0.0.1 --port 18000` in another terminal. With Chrome installed:

```bash
python -m pip install playwright
python tests/manual/verify_swagger_database.py --report-dir /tmp/readhead-swagger-check
```

This uses real Swagger **Try it out / Execute** buttons, actual HTTP requests, and independent PostgreSQL queries. It creates disposable accounts, checks committed changes, and deletes its own accounts. It also needs an available allowed `http://localhost:<port>` origin in `CORS_ORIGINS` for its temporary CORS fixture server. Reports and screenshots exclude passwords/tokens; a conversation is explicitly seeded as a database fixture, without pretending to be real AI output. Use a local development environment only.

See [.docs/development/implementation-status.md](.docs/development/implementation-status.md) for the current status and verification limits.
