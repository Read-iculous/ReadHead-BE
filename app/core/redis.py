"""Redis helpers with explicit outage degradation and owner-safe leases."""

import asyncio
import json
import logging
import secrets
import time
from contextlib import suppress

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings
from app.core.exceptions import AppException

client = Redis.from_url(
    get_settings().redis_url,
    decode_responses=True,
    socket_timeout=1.5,
    socket_connect_timeout=1.5,
)
logger = logging.getLogger(__name__)
RELEASE = "if redis.call('get',KEYS[1]) == ARGV[1] then return redis.call('del',KEYS[1]) else return 0 end"
RENEW = "if redis.call('get',KEYS[1]) == ARGV[1] then return redis.call('expire',KEYS[1],ARGV[2]) else return 0 end"


async def get_json(key: str) -> dict | None:
    """Read optional cached state; database checks remain authoritative."""
    try:
        value = await client.get(key)
        return json.loads(value) if value else None
    except (RedisError, ValueError):
        return None


async def set_json(key: str, value: dict, ttl: int) -> bool:
    """Store temporary state without logging its contents."""
    try:
        await client.set(key, json.dumps(value), ex=ttl)
        return True
    except RedisError:
        return False


async def mark(key: str, ttl: int = 3600) -> None:
    """Publish a best-effort revocation marker after a DB commit."""
    try:
        await client.set(key, "1", ex=ttl)
    except RedisError:
        logger.warning("redis_revocation_publish_unavailable")


async def mark_session_revoked(sid: str) -> None:
    """Keep session revocation longer than the maximum stream and access lifetime."""
    await mark(
        f"revoked_sessions:{sid}",
        max(240, get_settings().access_token_expire_minutes * 60 + 60),
    )


async def metric(field: str) -> None:
    """Increment one allowlisted aggregate counter without user content."""
    if field not in {"openai", "gemini", "claude", "errors"}:
        return
    try:
        key = f"metrics:{int(time.time() // 60)}"
        async with client.pipeline(transaction=True) as pipe:
            pipe.hincrby(key, field, 1)
            pipe.expire(key, 31 * 86400)
            await pipe.execute()
    except RedisError:
        pass


async def purge_grace(sid: str) -> None:
    """Delete only exact keys in this session's grace-cache index."""
    try:
        index = f"refresh_grace_keys:{sid}"
        keys = list(await client.smembers(index))
        await client.delete(index, *keys)
    except RedisError:
        logger.warning("redis_grace_cleanup_unavailable")


async def cache_pair(sid: str, old_hash: str, value: dict) -> None:
    """Index and cache one rotation result atomically in Redis."""
    key, index = f"refresh_grace:{sid}:{old_hash}", f"refresh_grace_keys:{sid}"
    try:
        async with client.pipeline(transaction=True) as pipe:
            pipe.set(key, json.dumps(value), ex=30)
            pipe.sadd(index, key)
            pipe.expire(index, 31)
            await pipe.execute()
    except RedisError:
        logger.warning("redis_rotation_cache_unavailable")


async def cache_private_quiz(uid: str, qid: str, value: dict) -> bool:
    """Atomically index private content; caller must hold the PostgreSQL user lock."""
    key, index = f"ephemeral_quiz:{qid}", f"ephemeral_quiz_keys:{uid}"
    try:
        async with client.pipeline(transaction=True) as pipe:
            pipe.set(key, json.dumps(value), ex=1800)
            pipe.sadd(index, key)
            pipe.expire(index, 1801)
            await pipe.execute()
        return True
    except RedisError:
        return False


async def purge_private_quizzes(uid: str) -> None:
    """Remove owned quizzes under the user lock, including legacy unindexed entries."""
    try:
        index = f"ephemeral_quiz_keys:{uid}"
        keys = set(await client.smembers(index))
        # Compatibility with still-live quizzes written before the index was introduced.
        # SCAN is incremental; only verified owned keys are deleted, never a wildcard.
        async for key in client.scan_iter(match="ephemeral_quiz:*", count=100):
            raw = await client.get(key)
            if raw:
                value = json.loads(raw)
                if isinstance(value, dict) and value.get("user_id") == uid:
                    keys.add(key)
        for key in keys:
            await client.delete(key)
        await client.delete(index)
    except (RedisError, ValueError, TypeError) as exc:
        raise AppException(
            503,
            "SERVICE_DEGRADED",
            "Personal cache cleanup is unavailable; retry deletion",
        ) from exc


class Mutex:
    """Owner-checked Redis optimization; PostgreSQL remains the final guard."""

    def __init__(self, key: str) -> None:
        self.key, self.owner, self.acquired = key, secrets.token_hex(16), False

    async def acquire(self, wait: float = 2, ttl: int = 5) -> bool:
        """Bound lock wait; return False to use DB locking on a Redis outage."""
        deadline = time.monotonic() + wait
        try:
            while True:
                if await client.set(self.key, self.owner, nx=True, ex=ttl):
                    self.acquired = True
                    return True
                if time.monotonic() >= deadline:
                    raise AppException(
                        503,
                        "REFRESH_TEMPORARILY_UNAVAILABLE",
                        "Refresh is in progress; try again",
                        headers={"Retry-After": "1"},
                    )
                await asyncio.sleep(0.05)
        except RedisError:
            return False

    async def release(self) -> None:
        """Never delete another owner's renewed lock."""
        if self.acquired:
            with suppress(RedisError):
                await client.eval(RELEASE, 1, self.key, self.owner)
            self.acquired = False


class StreamLease:
    """Heartbeat-backed user concurrency slot and conversation binding guard."""

    def __init__(self, user_id: str, conversation_id: str) -> None:
        self.user_id, self.cid = user_id, conversation_id
        self.owner = secrets.token_hex(16)
        self.task: asyncio.Task | None = None
        self.available, self.closed = True, False

    async def acquire(self) -> None:
        """Atomically reserve a conversation and one of two user slots."""
        script = """
        redis.call('zremrangebyscore', KEYS[1], '-inf', ARGV[1])
        if redis.call('exists', KEYS[2]) == 1 then return 2 end
        if redis.call('zcard', KEYS[1]) >= 2 then return 1 end
        redis.call('set', KEYS[2], ARGV[2], 'EX', 30)
        redis.call('zadd', KEYS[1], ARGV[3], ARGV[2])
        redis.call('expire', KEYS[1], 35)
        return 0
        """
        try:
            now = time.time()
            result = await client.eval(
                script,
                2,
                f"active_streams:{self.user_id}",
                f"conversation_stream:{self.user_id}:{self.cid}",
                now,
                self.owner,
                now + 30,
            )
            if result:
                code = (
                    "CONVERSATION_BUSY"
                    if result == 2
                    else "STREAM_CONCURRENCY_EXCEEDED"
                )
                raise AppException(
                    409 if result == 2 else 429,
                    code,
                    "Conversation or stream limit is busy",
                )
            self.task = asyncio.create_task(self._heartbeat())
        except RedisError:
            self.available = False

    async def _heartbeat(self) -> None:
        try:
            while True:
                await asyncio.sleep(8)
                renewed = await client.eval(
                    RENEW,
                    1,
                    f"conversation_stream:{self.user_id}:{self.cid}",
                    self.owner,
                    30,
                )
                if not renewed:
                    self.available = False
                    return
                await client.zadd(
                    f"active_streams:{self.user_id}", {self.owner: time.time() + 30}
                )
                await client.expire(f"active_streams:{self.user_id}", 35)
        except RedisError:
            self.available = False

    async def close(self) -> None:
        """Release the upstream operation's own slot, idempotently."""
        if self.closed:
            return
        self.closed = True
        if self.task:
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task
        with suppress(RedisError):
            await client.eval(
                RELEASE, 1, f"conversation_stream:{self.user_id}:{self.cid}", self.owner
            )
            await client.zrem(f"active_streams:{self.user_id}", self.owner)
