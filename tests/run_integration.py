"""Run the test suite with disposable Docker storage and explicitly mocked upstreams."""

import argparse
import base64
import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def run(report_dir: Path) -> int:
    """Generate test-only configuration, apply migrations and retain raw reports."""
    root = Path(__file__).resolve().parents[1]
    report_dir = report_dir.resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    suffix = secrets.token_hex(5)
    pg_name, redis_name = f"readhead-test-pg-{suffix}", f"readhead-test-redis-{suffix}"
    containers: list[str] = []
    password = secrets.token_urlsafe(24)
    env = dict(os.environ)
    try:
        for name, image, port, extra in [
            (
                pg_name,
                "postgres:15-alpine",
                5432,
                [
                    "--env",
                    "POSTGRES_USER=readhead_test",
                    "--env",
                    "POSTGRES_DB=readhead_test",
                    "--env",
                    "POSTGRES_PASSWORD",
                ],
            ),
            (redis_name, "redis:7-alpine", 6379, []),
        ]:
            subprocess.run(
                [
                    "docker",
                    "run",
                    "--detach",
                    "--rm",
                    "--name",
                    name,
                    "--publish",
                    f"127.0.0.1::{port}",
                    *extra,
                    image,
                ],
                env=dict(env, POSTGRES_PASSWORD=password),
                check=True,
                stdout=subprocess.DEVNULL,
            )
            containers.append(name)
        ports = [
            subprocess.check_output(["docker", "port", name, f"{port}/tcp"], text=True)
            .strip()
            .rsplit(":", 1)[1]
            for name, port in [(pg_name, 5432), (redis_name, 6379)]
        ]
        env.update(
            COVERAGE_FILE=str(report_dir / ".coverage"),
            DATABASE_URL=f"postgresql+asyncpg://readhead_test:{password}@127.0.0.1:{ports[0]}/readhead_test",
            REDIS_URL=f"redis://127.0.0.1:{ports[1]}/0",
            READHEAD_FULL_INTEGRATION="1",
            READHEAD_INTEGRATION_REDIS_URL=f"redis://127.0.0.1:{ports[1]}/0",
            JWT_SECRET_KEY=secrets.token_urlsafe(48),
            ENCRYPTION_MASTER_KEY=base64.b64encode(secrets.token_bytes(32)).decode(),
            ENCRYPTION_MASTER_KEYS="{}",
            CURRENT_KEY_VERSION="v1",
            GOOGLE_CLIENT_ID="",
            GOOGLE_CLIENT_SECRET="",
            GITHUB_CLIENT_ID="",
            GITHUB_CLIENT_SECRET="",
            AUTH_REQUESTS_PER_MINUTE="1000",
            API_REQUESTS_PER_MINUTE="1000",
            AI_REQUESTS_PER_MINUTE="1000",
            CORS_ORIGINS="chrome-extension://*,http://localhost:3000",
        )
        for _ in range(100):
            ready = subprocess.run(
                [
                    "docker",
                    "exec",
                    pg_name,
                    "pg_isready",
                    "-U",
                    "readhead_test",
                    "-d",
                    "readhead_test",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if ready.returncode == 0:
                break
            time.sleep(0.2)
        else:
            raise RuntimeError("Disposable PostgreSQL did not become ready")
        # Exercise the newest revision in both directions on disposable storage.
        for args in [
            ["upgrade", "head"],
            ["downgrade", "-1"],
            ["upgrade", "head"],
            ["check"],
        ]:
            result = subprocess.run(
                [sys.executable, "-m", "alembic", *args],
                cwd=root,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            with (report_dir / "migrations.log").open("a") as log:
                log.write("$ alembic " + " ".join(args) + "\n")
                log.write(result.stdout)
                log.write(f"Exit: {result.returncode}\n")
            result.check_returncode()
        (report_dir / "scope.json").write_text(
            json.dumps(
                {
                    "storage": "disposable real PostgreSQL 15 and Redis 7",
                    "api": "production FastAPI ASGI stack and real auth/services",
                    "upstream": "synthetic HTTP via MockTransport; installed AI SDK parsing is real",
                    "live_ai_oauth_verified": False,
                },
                indent=2,
            )
        )
        print("Reports:", report_dir, flush=True)
        command = [
            sys.executable,
            "-m",
            "pytest",
            "tests/",
            "-q",
            "--tb=short",
            "--cov=app",
            "--cov-report=term",
            "--cov-report=json:" + str(report_dir / "coverage.json"),
            "--junitxml=" + str(report_dir / "pytest.xml"),
        ]
        with (report_dir / "pytest.log").open("w") as log:
            result = subprocess.run(
                command,
                cwd=root,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )
        print((report_dir / "pytest.log").read_text())
        return result.returncode
    finally:
        for name in reversed(containers):
            subprocess.run(
                ["docker", "stop", name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", type=Path, default=None)
    args = parser.parse_args()
    raise SystemExit(
        run(args.report_dir or Path(tempfile.mkdtemp(prefix="readhead-integration-")))
    )
