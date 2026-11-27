"""Non-blocking Redis request limits with bounded process-local fallback."""

import hashlib
import time
from collections import OrderedDict

from redis.exceptions import RedisError

from app.core import redis
from app.core.exceptions import AppException

local_counts: OrderedDict = OrderedDict()


async def enforce_rate(identity: str, group: str, limit: int) -> None:
    """Apply a fixed one-minute window keyed by verified identity or trusted client IP."""
    now = int(time.time())
    window = now // 60
    key = f"rate:{group}:{hashlib.sha256(identity.encode()).hexdigest()}:{window}"
    try:
        count = await redis.client.eval(
            "local n=redis.call('incr',KEYS[1]); if n == 1 then redis.call('expire',KEYS[1],61) end return n",
            1,
            key,
        )
    except RedisError:
        count = local_counts.get(key, 0) + 1
        local_counts[key] = count
        local_counts.move_to_end(key)
        while len(local_counts) > 10000:
            local_counts.popitem(last=False)
    if count > limit:
        raise AppException(
            429,
            "RATE_LIMIT_EXCEEDED",
            "Request rate limit exceeded",
            headers={"Retry-After": str(60 - now % 60)},
        )
