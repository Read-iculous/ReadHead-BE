"""Bounded resource cleanup that survives an already-cancelled ASGI scope."""

import logging
import sys
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import AsyncContextManager, TypeVar

import anyio

T = TypeVar("T")
logger = logging.getLogger(__name__)
CLEANUP_TIMEOUT_SECONDS = 10


async def shielded_cleanup(callback: Callable[[], Awaitable[T]]) -> T | None:
    """Shield asynchronous release checkpoints while bounding stalled cleanup."""
    result: T | None = None
    with anyio.move_on_after(CLEANUP_TIMEOUT_SECONDS, shield=True) as scope:
        result = await callback()
    if scope.cancel_called:
        logger.warning("upstream_cleanup_timeout")
    return result


@asynccontextmanager
async def shielded_context(manager: AsyncContextManager[T]) -> AsyncIterator[T]:
    """Keep cancellation enabled during work and shield only context-manager exit."""
    resource = await manager.__aenter__()
    try:
        yield resource
    except BaseException:
        # Cancellation and GeneratorExit must retain normal async-with semantics.
        exception = sys.exc_info()
        suppressed = await shielded_cleanup(lambda: manager.__aexit__(*exception))
        if not suppressed:
            raise
    else:
        await shielded_cleanup(lambda: manager.__aexit__(None, None, None))
