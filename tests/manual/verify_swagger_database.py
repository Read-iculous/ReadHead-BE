"""Opt-in Chrome Swagger UI checks with independent PostgreSQL assertions.

Run from the repository root with a fresh local Uvicorn process and Playwright
installed. This script creates disposable accounts and removes only their rows.
It never calls an external AI/OAuth provider or records authentication secrets.
"""

import argparse
import asyncio
import base64
import hashlib
import json
import re
import secrets
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import asyncpg
import httpx
from playwright.async_api import Locator, async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core.config import get_settings  # noqa: E402


@contextmanager
def browser_origin_fixture(origins: str) -> Iterator[str]:
    """Serve a real loopback origin; keep Chrome's network security enabled."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            body = b"<html><title>ReadHead CORS browser test fixture</title></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    for origin in origins.split(","):
        origin = origin.strip()
        parsed = urlsplit(origin)
        if parsed.scheme != "http" or parsed.hostname != "localhost" or not parsed.port:
            continue
        try:
            server = ThreadingHTTPServer(("127.0.0.1", parsed.port), Handler)
        except OSError:
            continue
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield origin
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
        return
    raise RuntimeError("No free allowed localhost origin for the CORS browser fixture")


async def verify(base_url: str, report_dir: Path, chrome: str) -> None:
    """Execute actual Swagger buttons and validate independently committed rows."""
    cfg = get_settings()
    report_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "mode": "headless Chrome + Swagger Try it out + real TCP HTTP + PostgreSQL",
        "checks": [],
        "http_requests": [],
        "limitations": [
            "No successful real AI generation, provider-key validation, or OAuth login",
            "Conversation test row is an explicitly inserted fixture, not AI output",
            "No complete load/failure/concurrency testing",
        ],
    }
    emails = [f"swagger-check-{uuid4().hex}@example.com" for _ in range(2)]
    password = secrets.token_urlsafe(24)
    connection = await asyncpg.connect(
        cfg.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    )

    def check(name: str, condition: bool, observed: Any = None) -> None:
        row = {"name": name, "passed": bool(condition)}
        if observed is not None:
            row["observed"] = observed
        report["checks"].append(row)
        print(("PASS " if condition else "FAIL ") + name, flush=True)
        if not condition:
            raise AssertionError(name)

    try:
        tables = await connection.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
        )
        table_names = [r["tablename"] for r in tables]
        expected_tables = {
            "users",
            "oauth_accounts",
            "auth_sessions",
            "refresh_tokens",
            "user_api_keys",
            "user_settings",
            "conversations",
            "messages",
            "reading_history",
            "highlights",
            "quiz_records",
            "ai_feedback",
        }
        check(
            "PostgreSQL has all 12 domain tables",
            expected_tables <= set(table_names),
            table_names,
        )
        revision = await connection.fetchval("SELECT version_num FROM alembic_version")
        check(
            "Database migration is current",
            revision == "0002_domain_blacklist",
            revision,
        )

        async with httpx.AsyncClient(base_url=base_url) as direct:
            schema_response = await direct.get("/openapi.json")
            check("OpenAPI is served over HTTP", schema_response.status_code == 200)
            schema = schema_response.json()
            (report_dir / "openapi.json").write_text(json.dumps(schema, indent=2))
            operation_count = sum(
                method in {"get", "post", "patch", "delete", "put", "options", "head"}
                for path in schema["paths"].values()
                for method in path
            )
            for path, parameter in [
                ("/api/v1/reading/history", "search"),
                ("/api/v1/reading/highlights", "page_url"),
            ]:
                params = schema["paths"][path]["get"]["parameters"]
                check(
                    f"OpenAPI {parameter} filter is optional",
                    next(p for p in params if p["name"] == parameter)["required"]
                    is False,
                )
            reference = schema["paths"]["/api/v1/auth/register"]["post"]["responses"][
                "422"
            ]["content"]["application/json"]["schema"]["$ref"]
            documented_error = schema["components"]["schemas"][
                reference.rsplit("/", 1)[1]
            ]
            check(
                "Swagger documents the actual validation error envelope",
                documented_error["properties"]["detail"]["type"] == "string"
                and "code" in documented_error["required"],
            )

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                executable_path=chrome, headless=True, args=["--no-sandbox"]
            )
            context = await browser.new_context(
                viewport={"width": 1440, "height": 1000}
            )
            page = await context.new_page()
            page.set_default_timeout(15000)
            page_errors = []
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            await page.goto(base_url + "/docs")
            await page.wait_for_selector(".opblock", timeout=45000)
            check(
                "Swagger renders every OpenAPI operation in Chrome",
                await page.locator(".opblock").count() == operation_count,
                operation_count,
            )
            await page.screenshot(path=str(report_dir / "swagger-overview.png"))

            def operation(method: str, path: str) -> Locator:
                definition = schema["paths"][path][method.lower()]
                tag = re.sub(r"\W", "_", definition["tags"][0])
                return page.locator(
                    f'[id="operations-{tag}-{definition["operationId"]}"]'
                )

            async def execute(
                method: str,
                path: str,
                status: int,
                payload: dict[str, Any] | None = None,
                params: dict[str, Any] | None = None,
                code: str | None = None,
            ) -> dict[str, Any] | None:
                block = operation(method, path)
                if "is-open" not in (await block.get_attribute("class") or ""):
                    await block.locator(".opblock-summary").click()
                button = block.locator("button.try-out__btn:not(.reset)")
                await button.wait_for(state="visible")
                if (await button.inner_text()).strip() == "Try it out":
                    await button.click()
                if payload is not None:
                    await block.locator("textarea.body-param__text").fill(
                        json.dumps(payload)
                    )
                actual_path = path
                for name, value in (params or {}).items():
                    await block.locator(f'tr[data-param-name="{name}"] input').fill(
                        str(value)
                    )
                    actual_path = actual_path.replace("{" + name + "}", str(value))
                async with page.expect_response(
                    lambda response: response.request.method == method
                    and urlsplit(response.url).path == actual_path,
                    timeout=20000,
                ) as pending:
                    await block.get_by_role(
                        "button", name="Execute", exact=True
                    ).click()
                response = await pending.value
                result = await response.json() if response.status != 204 else None
                report["http_requests"].append(
                    {
                        "via": "Swagger UI Execute",
                        "method": method,
                        "path": actual_path,
                        "status": response.status,
                        "code": (
                            result.get("code") if isinstance(result, dict) else None
                        ),
                    }
                )
                check(
                    f"Swagger {method} {path} -> {status}",
                    response.status == status,
                    response.status,
                )
                if code:
                    check(
                        f"Response code {code}",
                        result.get("code") == code,
                        result.get("code"),
                    )
                # Collapse credential-bearing panels before taking any screenshots.
                await block.locator(".opblock-summary").click()
                return result

            async def authorize(token: str) -> None:
                await page.locator(".scheme-container").get_by_role(
                    "button", name="Authorize"
                ).click()
                modal = page.locator(".dialog-ux")
                await modal.locator(".auth-container").wait_for(state="visible")
                logout = modal.locator("button.auth").filter(
                    has_text=re.compile(r"^Logout$")
                )
                if await logout.count():
                    await logout.click()
                await modal.locator("input").fill(token)
                await modal.locator("button.auth.authorize").click()
                await modal.locator("button.btn-done").click()

            health = await execute("GET", "/api/v1/health", 200)
            check(
                "Readiness confirms real PostgreSQL and Redis",
                health["checks"]["database"]["status"] == "healthy"
                and health["checks"]["redis"]["status"] == "healthy",
            )
            await execute("GET", "/api/v1/health/live", 200)
            await execute("GET", "/api/v1/users/me", 401, code="UNAUTHORIZED")
            registration = {
                "email": emails[0],
                "password": password,
                "full_name": "Disposable Swagger Check",
            }
            await execute(
                "POST",
                "/api/v1/auth/register",
                422,
                {"email": "invalid", "password": "short"},
                code="VALIDATION_ERROR",
            )
            registered = await execute(
                "POST", "/api/v1/auth/register", 201, registration
            )
            uid = UUID(registered["data"]["id"])
            stored = await connection.fetchrow(
                "SELECT email, hashed_password FROM users WHERE id=$1", uid
            )
            check(
                "Registration committed user with bcrypt password, never plaintext",
                stored["email"] == emails[0]
                and stored["hashed_password"] != password
                and stored["hashed_password"].startswith("$2"),
            )
            check(
                "Registration committed default settings",
                await connection.fetchval(
                    "SELECT count(*) FROM user_settings WHERE user_id=$1 AND version=1",
                    uid,
                )
                == 1,
            )
            await execute(
                "POST",
                "/api/v1/auth/register",
                409,
                registration,
                code="EMAIL_ALREADY_EXISTS",
            )
            await execute(
                "POST",
                "/api/v1/auth/login",
                401,
                {"email": emails[0], "password": "wrong-password"},
                code="INVALID_CREDENTIALS",
            )
            await execute(
                "POST",
                "/api/v1/auth/login",
                422,
                {"email": emails[0], "password": "😀" * 18 + "x"},
                code="VALIDATION_ERROR",
            )
            login = (
                await execute(
                    "POST",
                    "/api/v1/auth/login",
                    200,
                    {"email": emails[0], "password": password},
                )
            )["data"]
            refresh_hash = hashlib.sha256(login["refresh_token"].encode()).hexdigest()
            token_row = await connection.fetchrow(
                "SELECT session_id, token_hash FROM refresh_tokens WHERE user_id=$1",
                uid,
            )
            check(
                "Login stored only SHA-256 refresh token hash",
                token_row["token_hash"] == refresh_hash,
            )
            sid = token_row["session_id"]
            check(
                "Login committed active auth session",
                await connection.fetchval(
                    "SELECT count(*) FROM auth_sessions WHERE id=$1 AND user_id=$2 AND revoked_at IS NULL",
                    sid,
                    uid,
                )
                == 1,
            )
            await authorize(login["access_token"])
            profile = await execute("GET", "/api/v1/users/me", 200)
            check(
                "Authenticated profile matches PostgreSQL user",
                profile["data"]["id"] == str(uid)
                and profile["data"]["email"] == stored["email"],
            )
            await execute("GET", "/api/v1/users/me/settings", 200)
            await execute(
                "PATCH",
                "/api/v1/users/me/settings",
                200,
                {"version": 1, "target_language": "en"},
            )
            await execute(
                "PATCH",
                "/api/v1/users/me/settings",
                409,
                {"version": 1, "target_language": "fr"},
                code="SYNC_CONFLICT",
            )
            settings = await connection.fetchrow(
                "SELECT version,target_language FROM user_settings WHERE user_id=$1",
                uid,
            )
            check(
                "Stale settings update leaves committed version unchanged",
                dict(settings) == {"version": 2, "target_language": "en"},
                dict(settings),
            )

            source = {
                "page_url": "https://example.com/swagger-check",
                "page_title": "Swagger database verification",
                "reading_time_seconds": 45,
            }
            await execute("POST", "/api/v1/reading/history", 201, source)
            history = await execute("GET", "/api/v1/reading/history", 200)
            check(
                "History without search agrees with committed row",
                history["data"]["total"] == 1
                and await connection.fetchval(
                    "SELECT count(*) FROM reading_history WHERE user_id=$1 AND reading_time_seconds=45",
                    uid,
                )
                == 1,
            )
            highlight = {
                "page_url": source["page_url"],
                "highlighted_text": "A real PostgreSQL saved highlight",
                "user_note": "Temporary test note",
                "color": "yellow",
            }
            saved = (
                await execute("POST", "/api/v1/reading/highlights", 201, highlight)
            )["data"]
            hid = UUID(saved["id"])
            listing = await execute("GET", "/api/v1/reading/highlights", 200)
            check(
                "Highlights without URL filter agrees with PostgreSQL",
                listing["data"]["total"] == 1
                and await connection.fetchval(
                    "SELECT highlighted_text FROM highlights WHERE id=$1 AND user_id=$2",
                    hid,
                    uid,
                )
                == highlight["highlighted_text"],
            )
            block = operation("GET", "/api/v1/reading/highlights")
            await block.locator(".opblock-summary").click()
            await block.locator(".live-responses-table").screenshot(
                path=str(report_dir / "swagger-highlights-response.png")
            )
            await block.locator(".opblock-summary").click()

            first_pull = (
                await execute("POST", "/api/v1/sync/pull", 200, {"limit": 1})
            )["data"]
            check(
                "Unified sync uses real combined-row pagination",
                first_pull["has_more"] and first_pull["total_items_in_page"] == 1,
            )
            second_pull = (
                await execute(
                    "POST",
                    "/api/v1/sync/pull",
                    200,
                    {"cursor": first_pull["next_cursor"], "limit": 1},
                )
            )["data"]
            check(
                "Second sync page completes exactly two persisted entities",
                not second_pull["has_more"] and second_pull["total_items_in_page"] == 1,
            )
            checkpoint = second_pull["next_cursor"]
            empty = (
                await execute("POST", "/api/v1/sync/pull", 200, {"cursor": checkpoint})
            )["data"]
            check(
                "Unchanged checkpoint returns no mutations",
                empty["total_items_in_page"] == 0,
            )
            mutation = {
                "entity_type": "highlight",
                "action": "update",
                "entity_id": str(hid),
                "base_version": 1,
                "payload": {"color": "blue"},
            }
            await execute("POST", "/api/v1/sync/push", 200, {"mutations": [mutation]})
            await execute(
                "POST",
                "/api/v1/sync/push",
                409,
                {"mutations": [mutation]},
                code="SYNC_CONFLICT",
            )
            atomic = [
                {**mutation, "base_version": 2, "payload": {"color": "pink"}},
                {**mutation, "entity_id": str(uuid4())},
            ]
            await execute(
                "POST",
                "/api/v1/sync/push",
                400,
                {"mutations": atomic},
                code="INVALID_SYNC_MUTATION",
            )
            db_highlight = await connection.fetchrow(
                "SELECT version,color FROM highlights WHERE id=$1", hid
            )
            check(
                "Failed sync batch rolls back earlier mutation in PostgreSQL",
                dict(db_highlight) == {"version": 2, "color": "blue"},
                dict(db_highlight),
            )
            bad_cursor = base64.urlsafe_b64encode(
                json.dumps({"v": 1, "kind": "checkpoint", "t": 1, "anchor": 1}).encode()
            ).decode()
            await execute(
                "POST",
                "/api/v1/sync/pull",
                400,
                {"cursor": bad_cursor},
                code="INVALID_SYNC_CURSOR",
            )

            await execute(
                "PATCH",
                "/api/v1/users/me/settings",
                200,
                {"version": 2, "privacy_mode_enabled": True},
            )
            skipped = await execute(
                "POST",
                "/api/v1/reading/history",
                200,
                {**source, "page_url": "https://example.com/private-check"},
            )
            check(
                "Privacy Mode skips database history writes",
                skipped["data"] is None
                and await connection.fetchval(
                    "SELECT count(*) FROM reading_history WHERE user_id=$1", uid
                )
                == 1,
            )
            await execute(
                "POST",
                "/api/v1/reading/highlights",
                201,
                {**highlight, "highlighted_text": "Explicit private-mode save"},
            )
            check(
                "Explicit Save Highlight persists during Privacy Mode",
                await connection.fetchval(
                    "SELECT count(*) FROM highlights WHERE user_id=$1", uid
                )
                == 2,
            )
            await execute(
                "PATCH",
                "/api/v1/users/me/settings",
                200,
                {
                    "version": 3,
                    "privacy_mode_enabled": False,
                    "blacklisted_domains": ["blocked.example.com"],
                },
            )
            await execute(
                "POST",
                "/api/v1/reading/history",
                200,
                {**source, "page_url": "https://blocked.example.com/private"},
            )
            check(
                "Blacklisted domain does not add database history rows",
                await connection.fetchval(
                    "SELECT count(*) FROM reading_history WHERE user_id=$1", uid
                )
                == 1,
            )
            sensitive = (
                await execute(
                    "POST",
                    "/api/v1/ai/check-sensitive",
                    200,
                    {"text": "Contact reader@example.com"},
                )
            )["data"]
            check(
                "PII preflight blocks and redacts email",
                sensitive["blocked_by_policy"]
                and "reader@example.com" not in sensitive["redacted_preview"],
            )
            await execute("GET", "/api/v1/api-keys", 200)
            await execute(
                "POST",
                "/api/v1/ai/stream",
                400,
                {
                    "task": "explain",
                    "page_url": source["page_url"],
                    "selected_text": "A harmless test paragraph",
                },
                code="NO_ACTIVE_API_KEY",
            )
            check(
                "Missing key causes no conversations or messages to be written",
                await connection.fetchval(
                    "SELECT count(*) FROM conversations WHERE user_id=$1", uid
                )
                == 0,
            )
            await execute(
                "GET", "/api/v1/admin/telemetry", 403, code="FORBIDDEN_RESOURCE"
            )

            # Explicit database fixture: exercise history/binding without claiming AI output.
            cid = uuid4()
            await connection.execute(
                "INSERT INTO conversations (id,user_id,title,page_url,page_title) VALUES ($1,$2,$3,$4,$5)",
                cid,
                uid,
                "Explicit test fixture",
                source["page_url"],
                source["page_title"],
            )
            await execute("GET", "/api/v1/conversations", 200)
            await execute(
                "GET", "/api/v1/conversations/{id}/messages", 200, params={"id": cid}
            )
            reading_session = uuid4()
            await execute(
                "POST",
                "/api/v1/ai/conversations/{id}/bind",
                200,
                {
                    "page_url": source["page_url"],
                    "reading_session_id": str(reading_session),
                },
                {"id": cid},
            )
            check(
                "Bind updates the PostgreSQL reading session",
                await connection.fetchval(
                    "SELECT reading_session_id FROM conversations WHERE id=$1", cid
                )
                == reading_session,
            )
            await execute(
                "POST",
                "/api/v1/ai/conversations/{id}/bind",
                400,
                {
                    "page_url": "https://other.example.com",
                    "reading_session_id": str(uuid4()),
                },
                {"id": cid},
                "TAB_CONTEXT_MISMATCH",
            )
            check(
                "Rejected binding preserves PostgreSQL reading session",
                await connection.fetchval(
                    "SELECT reading_session_id FROM conversations WHERE id=$1", cid
                )
                == reading_session,
            )
            await execute("DELETE", "/api/v1/reading/history", 204)
            anonymized = await connection.fetchrow(
                "SELECT page_url,page_title,version FROM conversations WHERE id=$1", cid
            )
            check(
                "Clear history removes visits and anonymizes conversation fixture",
                await connection.fetchval(
                    "SELECT count(*) FROM reading_history WHERE user_id=$1", uid
                )
                == 0
                and anonymized["page_url"] is None
                and anonymized["page_title"] is None
                and anonymized["version"] > 1,
            )
            await execute(
                "DELETE", "/api/v1/reading/highlights/{id}", 204, params={"id": hid}
            )
            check(
                "Delete highlight creates versioned PostgreSQL tombstone",
                await connection.fetchval(
                    "SELECT is_deleted AND version=3 FROM highlights WHERE id=$1", hid
                )
                is True,
            )
            delta = (
                await execute("POST", "/api/v1/sync/pull", 200, {"cursor": checkpoint})
            )["data"]
            check(
                "Incremental sync returns committed deletion tombstone",
                any(
                    r["id"] == str(hid) and r["is_deleted"] and r["version"] == 3
                    for r in delta["updated_highlights"]
                ),
            )
            await execute(
                "DELETE", "/api/v1/conversations/{id}", 204, params={"id": cid}
            )
            await execute(
                "GET",
                "/api/v1/conversations/{id}/messages",
                404,
                params={"id": cid},
                code="CONVERSATION_NOT_FOUND",
            )

            # A second actual account must not access the first account's objects.
            second = await execute(
                "POST",
                "/api/v1/auth/register",
                201,
                {**registration, "email": emails[1]},
            )
            uid2 = UUID(second["data"]["id"])
            second_login = (
                await execute(
                    "POST",
                    "/api/v1/auth/login",
                    200,
                    {"email": emails[1], "password": password},
                )
            )["data"]
            await authorize(second_login["access_token"])
            other_list = await execute("GET", "/api/v1/reading/highlights", 200)
            check(
                "Second account cannot list first account highlights",
                other_list["data"]["total"] == 0,
            )
            await execute(
                "DELETE",
                "/api/v1/reading/highlights/{id}",
                404,
                params={"id": hid},
                code="HIGHLIGHT_NOT_FOUND",
            )
            await execute(
                "DELETE",
                "/api/v1/users/me",
                204,
                {"confirmation": "DELETE_ACCOUNT", "password": password},
            )
            check(
                "Second test account removed through API",
                await connection.fetchval(
                    "SELECT count(*) FROM users WHERE id=$1", uid2
                )
                == 0,
            )
            await authorize(login["access_token"])

            rotated = (
                await execute(
                    "POST",
                    "/api/v1/auth/refresh",
                    200,
                    {"refresh_token": login["refresh_token"]},
                )
            )["data"]
            old_token = await connection.fetchrow(
                "SELECT is_revoked,revocation_reason,replaced_by_token_id FROM refresh_tokens WHERE user_id=$1 AND token_hash=$2",
                uid,
                refresh_hash,
            )
            check(
                "Refresh rotation revokes predecessor and links replacement",
                old_token["is_revoked"]
                and old_token["revocation_reason"] == "rotated"
                and old_token["replaced_by_token_id"] is not None,
            )
            replay = (
                await execute(
                    "POST",
                    "/api/v1/auth/refresh",
                    200,
                    {"refresh_token": login["refresh_token"]},
                )
            )["data"]
            check(
                "Refresh grace replay returns the same replacement",
                replay["refresh_token"] == rotated["refresh_token"],
            )
            await authorize(rotated["access_token"])
            await execute(
                "POST",
                "/api/v1/auth/logout",
                204,
                {"refresh_token": rotated["refresh_token"]},
            )
            check(
                "Logout revokes authoritative database session and all tokens",
                await connection.fetchval(
                    "SELECT revoked_at IS NOT NULL AND revocation_reason='logout' FROM auth_sessions WHERE id=$1",
                    sid,
                )
                and await connection.fetchval(
                    "SELECT count(*) FROM refresh_tokens WHERE session_id=$1 AND NOT is_revoked",
                    sid,
                )
                == 0,
            )
            await execute("GET", "/api/v1/users/me", 401, code="UNAUTHORIZED")
            final_login = (
                await execute(
                    "POST",
                    "/api/v1/auth/login",
                    200,
                    {"email": emails[0], "password": password},
                )
            )["data"]
            await authorize(final_login["access_token"])
            await execute(
                "DELETE",
                "/api/v1/users/me",
                204,
                {"confirmation": "DELETE_ACCOUNT", "password": password},
            )
            dependent_counts = {}
            for table in sorted(expected_tables - {"users", "messages"}):
                dependent_counts[table] = await connection.fetchval(
                    f'SELECT count(*) FROM "{table}" WHERE user_id=$1', uid
                )
            dependent_counts["users"] = await connection.fetchval(
                "SELECT count(*) FROM users WHERE id=$1", uid
            )
            dependent_counts["messages"] = await connection.fetchval(
                "SELECT count(*) FROM messages WHERE conversation_id=$1", cid
            )
            check(
                "Account deletion cascades all test-owned PostgreSQL rows",
                not any(dependent_counts.values()),
                dependent_counts,
            )

            # Actual loopback HTTP source avoids synthetic-origin address-space errors.
            with browser_origin_fixture(cfg.cors_origins) as allowed:
                cors_page = await context.new_page()
                fixture_url = allowed + "/readhead-cors-browser-fixture"
                await cors_page.goto(fixture_url)
                cors = await cors_page.evaluate(
                    """async ({url, attempts}) => {
                    for (let i=0; i<attempts; i++) {
                        const r = await fetch(url+'/api/v1/auth/login', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
                        const body = await r.json();
                        if (r.status === 429) return {status:r.status, code:body.code, retry:r.headers.get('Retry-After'), requestId:!!r.headers.get('X-Request-ID'), attempts:i+1};
                    }
                    return {status:null};
                }""",
                    {"url": base_url, "attempts": cfg.auth_requests_per_minute + 1},
                )
                check(
                    "Chrome cross-origin JavaScript can read real Redis-limited 429 and exposed headers",
                    cors.get("status") == 429
                    and cors.get("code") == "RATE_LIMIT_EXCEEDED"
                    and cors.get("requestId")
                    and 1 <= int(cors.get("retry") or 0) <= 60,
                    cors,
                )
            check(
                "Swagger has no uncaught JavaScript errors",
                not page_errors,
                page_errors,
            )
            await browser.close()
        report["completed"] = True
    except BaseException as exc:
        report["completed"] = False
        # Record only error type: browser diagnostics can include credential text.
        report["failure_type"] = type(exc).__name__
        raise
    finally:
        try:
            # Fallback cleanup is restricted to generated exact email addresses.
            result = await connection.execute(
                "DELETE FROM users WHERE email=ANY($1::text[])", emails
            )
            remaining = await connection.fetchval(
                "SELECT count(*) FROM users WHERE email=ANY($1::text[])", emails
            )
            report["cleanup"] = {
                "fallback_delete_result": result,
                "remaining_test_accounts": remaining,
            }
        finally:
            await connection.close()
            report["finished_at"] = datetime.now(timezone.utc).isoformat()
            (report_dir / "results.json").write_text(
                json.dumps(report, indent=2, default=str)
            )
            print("Report directory:", report_dir, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:18000")
    parser.add_argument("--report-dir", required=True, type=Path)
    parser.add_argument("--chrome", default="/usr/bin/google-chrome")
    arguments = parser.parse_args()
    if urlsplit(arguments.base_url).hostname not in {"127.0.0.1", "localhost"}:
        parser.error("Use a local development server only")
    asyncio.run(
        verify(arguments.base_url.rstrip("/"), arguments.report_dir, arguments.chrome)
    )
