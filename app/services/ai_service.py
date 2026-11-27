"""Source-grounded AI orchestration with short DB transactions and SSE lifetime cleanup."""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from fastapi.encoders import jsonable_encoder
from redis.exceptions import RedisError
from sqlalchemy import select

from app.core import redis
from app.core.ai.base import BaseAIProvider
from app.core.ai.cleanup import shielded_cleanup
from app.core.ai.errors import provider_error
from app.core.ai.factory import DEFAULT_MODELS, ProviderFactory
from app.core.ai.grounding import attribution, build_messages
from app.core.auth import Principal
from app.core.database import transaction
from app.core.exceptions import AppException
from app.models.conversation import Conversation, Message
from app.schemas.ai import AiStreamRequest, ProactiveSuggestRequest
from app.schemas.common import validate_postgres_text
from app.services.api_key_service import active_key
from app.services.common import owned, settings_for, sync_stamp
from app.services.privacy_service import enforce

logger = logging.getLogger(__name__)


@dataclass
class PreparedStream:
    """Private request-local state; never log or serialize this object."""

    cid: UUID
    mid: UUID
    private: bool
    provider_name: str
    model: str
    provider: BaseAIProvider = field(repr=False)
    messages: list = field(repr=False)
    sources: dict = field(repr=False)
    lease: redis.StreamLease = field(repr=False)


async def prepare(principal: Principal, data: AiStreamRequest) -> PreparedStream:
    """Validate outbound policy before persisting a turn or starting HTTP streaming."""
    cid = data.conversation_id or uuid4()
    async with transaction() as db:
        settings = await settings_for(db, principal.user_id)
        private = settings.privacy_mode_enabled
        if data.ephemeral_history and not private:
            raise AppException(
                422,
                "VALIDATION_ERROR",
                "ephemeral_history is only allowed in Privacy Mode",
                "ephemeral_history",
            )
        history = [t.model_dump() for t in data.ephemeral_history] if private else []
        if not private and data.conversation_id:
            await owned(
                db, Conversation, cid, principal.user_id, "CONVERSATION_NOT_FOUND"
            )
        outbound = "\n".join(
            [
                data.page_content,
                data.selected_text,
                data.user_prompt,
                *[t["content"] for t in history],
            ]
        )
        enforce(settings, data.page_url, outbound, data.bypass_protection)
        if data.task in {"summarize", "simplify", "translate"} and not (
            data.page_content.strip() or data.selected_text.strip()
        ):
            raise AppException(
                422,
                "UNREPRESENTATIVE_SOURCE",
                "Provide source text for this reading task",
            )
        provider_name = data.provider or settings.default_provider
        model = data.model or (
            settings.default_model
            if provider_name == settings.default_provider
            else DEFAULT_MODELS[provider_name]
        )
        key = await active_key(db, principal.user_id, provider_name)
    lease = redis.StreamLease(str(principal.user_id), str(cid))
    try:
        async with transaction() as db:
            # Bind/stream admission share this user-row lock, closing their race window.
            stamp = await sync_stamp(db, principal.user_id)
            from app.services.auth_service import checked_session

            await checked_session(db, principal.user_id, principal.session_id, False)
            current_settings = await settings_for(db, principal.user_id)
            if current_settings.privacy_mode_enabled and not private:
                # Privacy became active after the first read. Use only private input.
                private = True
                history = [turn.model_dump() for turn in data.ephemeral_history]
            if not private:
                if data.conversation_id:
                    conv = await owned(
                        db,
                        Conversation,
                        cid,
                        principal.user_id,
                        "CONVERSATION_NOT_FOUND",
                        True,
                    )
                    if (
                        conv.reading_session_id is None
                        or data.reading_session_id is None
                        or conv.reading_session_id != data.reading_session_id
                    ):
                        raise AppException(
                            400,
                            "TAB_CONTEXT_MISMATCH",
                            "Explicitly bind this reading session before continuing",
                        )
                    if conv.page_url and conv.page_url != data.page_url:
                        raise AppException(
                            400,
                            "TAB_CONTEXT_MISMATCH",
                            "Page URL does not match the conversation",
                        )
                else:
                    conv = Conversation(
                        id=cid,
                        user_id=principal.user_id,
                        reading_session_id=data.reading_session_id,
                        page_url=data.page_url,
                        page_title=data.page_title,
                        title=(
                            data.page_title or data.user_prompt or "New Conversation"
                        )[:255],
                        updated_at=stamp,
                    )
                    db.add(conv)
                    await db.flush()
                await lease.acquire()
                # The preceding stream may have committed after the initial read.
                previous = (
                    await db.scalars(
                        select(Message)
                        .where(Message.conversation_id == cid)
                        .order_by(Message.created_at.desc(), Message.id.desc())
                        .limit(10)
                    )
                ).all()
                history = [
                    dict(role=row.sender_role, content=row.content)
                    for row in reversed(previous)
                    if row.sender_role in {"user", "assistant"}
                ]
            else:
                await lease.acquire()
            enforce(
                current_settings,
                data.page_url,
                "\n".join(
                    [
                        data.page_content,
                        data.selected_text,
                        data.user_prompt,
                        *[turn["content"] for turn in history],
                    ]
                ),
                data.bypass_protection,
            )
            messages, sources = build_messages(
                data.task,
                data.page_content,
                data.selected_text,
                data.user_prompt,
                history,
                data.target_language or current_settings.target_language,
                current_settings.explanation_level,
            )
            if not private:
                db.add(
                    Message(
                        conversation_id=cid,
                        sender_role="user",
                        content=data.user_prompt or data.task,
                        selected_context=data.selected_text or None,
                        created_at=stamp,
                    )
                )
                conv.version += 1
                conv.updated_at = stamp
        return PreparedStream(
            cid,
            uuid4(),
            private,
            provider_name,
            model,
            ProviderFactory.create(provider_name, key),
            messages,
            sources,
            lease,
        )
    except BaseException:
        await shielded_cleanup(lease.close)
        raise


async def persist(
    principal: Principal, prepared: PreparedStream, text: str, metadata: dict
) -> None:
    """Commit assistant output before done; skip every content write in Privacy Mode."""
    if prepared.private or not text:
        return
    async with transaction() as db:
        stamp = await sync_stamp(db, principal.user_id)
        if (await settings_for(db, principal.user_id)).privacy_mode_enabled:
            # Also guards disconnect partial writes; once private, stay ephemeral.
            prepared.private = True
            return
        conv = await owned(
            db,
            Conversation,
            prepared.cid,
            principal.user_id,
            "CONVERSATION_NOT_FOUND",
            True,
        )
        db.add(
            Message(
                id=prepared.mid,
                conversation_id=conv.id,
                sender_role="assistant",
                content=text,
                provider_used=prepared.provider_name,
                model_used=prepared.model,
                created_at=stamp,
                **metadata,
            )
        )
        conv.version += 1
        conv.updated_at = stamp


def event(name: str, value: dict) -> str:
    """Encode SSE without allowing content to inject event delimiters."""
    return f"event: {name}\ndata: {json.dumps(jsonable_encoder(value),ensure_ascii=False)}\n\n"


async def check_stream_revocation(principal: Principal) -> None:
    """Check sticky per-session revocation without opening a streaming DB session."""
    try:
        if await redis.client.exists(f"revoked_users:{principal.user_id}"):
            raise AppException(401, "USER_SUSPENDED", "Account was suspended")
        if await redis.client.exists(f"revoked_sessions:{principal.session_id}"):
            raise AppException(401, "UNAUTHORIZED", "Session has ended")
    except RedisError:
        pass  # ADR-010: declared degraded-stream policy.


async def generate(
    principal: Principal, prepared: PreparedStream
) -> AsyncGenerator[str, None]:
    """Yield tokens, then commit, and close the provider on every exit path."""
    chunks = []
    persisted = False
    size = 0
    upstream = prepared.provider.generate_stream(prepared.messages, prepared.model)
    try:
        await redis.metric(prepared.provider_name)
        yield event(
            "start", dict(conversation_id=prepared.cid, message_id=prepared.mid)
        )
        async for token in bounded_tokens(upstream):
            await check_stream_revocation(principal)
            validate_postgres_text(token)
            size += len(token)
            if size > 100000:
                raise AppException(
                    502,
                    "UPSTREAM_AI_ERROR",
                    "Provider output exceeded the safe limit",
                )
            chunks.append(token)
            yield event("token", dict(content=token, index=len(chunks) - 1))
        text = "".join(chunks)
        await check_stream_revocation(principal)
        if not text.strip():
            raise AppException(
                502, "UPSTREAM_AI_ERROR", "Provider returned no usable text"
            )
        finish_reason = prepared.provider.finish_reason
        if finish_reason not in {"stop", "length"}:
            raise AppException(
                502,
                "UPSTREAM_AI_ERROR",
                "Provider did not complete a usable response; retry manually",
            )
        metadata, citations = attribution(text, prepared.sources)
        if finish_reason == "length":
            metadata.update(
                is_grounded=False,
                uncertainty_flag=True,
                grounding_notes="truncated_by_provider: output token limit reached",
            )
        for citation in citations:
            yield event("citation", citation)
        try:
            await persist(principal, prepared, text, metadata)
            persisted = True
        except Exception as exc:
            logger.warning("assistant_persistence_failed")
            raise AppException(
                500,
                "PERSISTENCE_FAILED",
                "Failed to persist response; keep this text in the current UI and copy it",
            ) from exc
        yield event(
            "done",
            dict(
                message_id=prepared.mid,
                finish_reason=finish_reason,
                provider=prepared.provider_name,
                model=prepared.model,
                total_tokens=None,
                **metadata,
            ),
        )
    except (asyncio.CancelledError, GeneratorExit):
        # Stop token consumption before doing any best-effort partial DB write.
        await shielded_cleanup(upstream.aclose)
        if chunks and not persisted and not prepared.private:
            try:
                await shielded_cleanup(
                    lambda: persist(
                        principal,
                        prepared,
                        "".join(chunks),
                        dict(
                            is_grounded=False,
                            uncertainty_flag=True,
                            grounding_notes="interrupted_by_client",
                        ),
                    )
                )
            except Exception:
                logger.warning("partial_response_persistence_failed")
        raise
    except AppException as exc:
        await redis.metric("errors")
        yield event("error", exc.payload())
    except TimeoutError:
        await redis.metric("errors")
        yield event(
            "error",
            dict(
                code="UPSTREAM_AI_TIMEOUT",
                detail="AI request timed out; retry manually",
            ),
        )
    except Exception as exc:
        await redis.metric("errors")
        logger.warning("stream_generation_failed")
        # SDKs can expose transport errors directly while consuming response bytes.
        yield event("error", provider_error(exc).payload())
    finally:
        try:
            await shielded_cleanup(upstream.aclose)
        finally:
            try:
                await shielded_cleanup(prepared.lease.close)
            finally:
                prepared.provider.key = ""
                prepared.messages.clear()
                prepared.sources.clear()
                chunks.clear()


async def complete_source(
    principal: Principal, url: str, text: str, instruction: str, bypass: bool
) -> str:
    """Run non-streaming quiz/proactive generation through the same policy and key gateway."""
    async with transaction() as db:
        settings = await settings_for(db, principal.user_id)
        enforce(settings, url, text, bypass)
        key = await active_key(db, principal.user_id, settings.default_provider)
        provider = ProviderFactory.create(settings.default_provider, key)
        model = settings.default_model
        messages, _ = build_messages(
            "chat",
            text,
            "",
            instruction,
            [],
            settings.target_language,
            settings.explanation_level,
        )
    await redis.metric(settings.default_provider)
    try:
        return await asyncio.wait_for(
            provider.generate_complete(messages, model), timeout=90
        )
    except TimeoutError as exc:
        raise AppException(
            504, "UPSTREAM_AI_TIMEOUT", "AI provider timed out; retry manually"
        ) from exc
    except AppException:
        raise
    except Exception as exc:
        raise provider_error(exc) from exc
    finally:
        provider.key = ""
        messages.clear()


async def proactive(principal: Principal, data: ProactiveSuggestRequest) -> dict:
    """Respect opt-out and sensitivity; suggestions never execute the suggested action."""
    async with transaction() as db:
        settings = await settings_for(db, principal.user_id)
        threshold = {"low": 45, "medium": 25, "high": 15}[
            settings.proactive_sensitivity
        ]
        if (
            not settings.proactive_assistance_enabled
            or data.dwell_time_seconds < threshold
        ):
            return {"data": {"has_suggestion": False}}
    hint = await complete_source(
        principal,
        data.page_url,
        data.paragraph_text,
        "Return one short optional hint (at most two sentences) about the hardest concept. Do not perform any action.",
        data.bypass_protection,
    )
    return {
        "data": dict(
            has_suggestion=True,
            suggestion_type="key_concept",
            hint=hint[:1000],
            suggested_action="explain",
        )
    }


async def bounded_tokens(
    upstream: AsyncGenerator[str, None],
) -> AsyncGenerator[str, None]:
    """Bound both total generation duration and stalled token reads on Python 3.10+."""
    import time

    deadline = time.monotonic() + 180
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError()
        try:
            token = await asyncio.wait_for(
                upstream.__anext__(), timeout=min(45, remaining)
            )
        except StopAsyncIteration:
            return
        yield token
