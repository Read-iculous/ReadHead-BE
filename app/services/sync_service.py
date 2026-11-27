"""Unified latest-state sync with monotonic commit ordering and atomic mutations."""

import base64
import binascii
import json
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import literal, select, tuple_, union_all, update
from sqlalchemy.sql import func

from app.core.auth import Principal
from app.core.database import transaction
from app.core.exceptions import AppException
from app.core.security import utcnow
from app.models.conversation import Conversation
from app.models.highlight import Highlight
from app.models.user_setting import UserSetting
from app.schemas.common import public, validate_postgres_text
from app.schemas.reading import HighlightCreate
from app.schemas.sync import SyncPullRequest, SyncPushRequest
from app.schemas.user import UserSettingUpdateRequest
from app.services.common import (
    CONVERSATION_FIELDS,
    HIGHLIGHT_FIELDS,
    SETTINGS_FIELDS,
    settings_values,
    sync_stamp,
)

ENTITIES: dict[str, tuple[Any, tuple[str, ...]]] = {
    "conversation": (Conversation, CONVERSATION_FIELDS),
    "highlight": (Highlight, HIGHLIGHT_FIELDS),
    "settings": (UserSetting, SETTINGS_FIELDS),
}


def encode_cursor(value: dict) -> str:
    """Encode an opaque versioned checkpoint without exposing internal DB sessions."""
    return base64.urlsafe_b64encode(
        json.dumps(value, separators=(",", ":")).encode()
    ).decode()


def decode_cursor(value: str | None) -> dict | None:
    """Validate the entire cursor structure, timestamps, tuple type and identity."""
    if value is None:
        return None
    try:
        if not isinstance(value, str):
            raise ValueError()
        row = json.loads(base64.b64decode(value, altchars=b"-_", validate=True))
        if (
            not isinstance(row, dict)
            or type(row.get("v")) is not int
            or row.get("v") != 1
            or not isinstance(row.get("kind"), str)
            or row.get("kind") not in {"position", "checkpoint"}
        ):
            raise ValueError()
        keys = {"v", "kind", "t", "anchor"} | (
            {"entity_type", "id"} if row["kind"] == "position" else set()
        )
        if set(row) != keys:
            raise ValueError()
        for name in ("t", "anchor"):
            if not isinstance(row[name], str):
                raise ValueError()
            row[name] = datetime.fromisoformat(row[name].replace("Z", "+00:00"))
            if row[name].tzinfo is None or row[name] > utcnow() + timedelta(seconds=60):
                raise ValueError()
        if row["kind"] == "position":
            if (
                not isinstance(row["entity_type"], str)
                or row["entity_type"] not in ENTITIES
            ):
                raise ValueError()
            if not isinstance(row["id"], str):
                raise ValueError()
            row["id"] = UUID(row["id"])
        if row["anchor"] < utcnow() - timedelta(days=30):
            raise AppException(
                410,
                "CURSOR_EXPIRED",
                "Sync checkpoint expired; preserve local drafts and pending work",
                field="cursor",
                requires_full_sync=True,
            )
        return row
    except (ValueError, TypeError, KeyError, binascii.Error) as exc:
        raise AppException(
            400, "INVALID_SYNC_CURSOR", "Invalid sync cursor", "cursor"
        ) from exc


async def pull(principal: Principal, data: SyncPullRequest) -> dict:
    """Merge three entity groups before slicing and advance empty checkpoints."""
    cursor = decode_cursor(data.cursor)
    anchor = cursor["anchor"] if cursor else utcnow()
    async with transaction() as db:
        checkpoint = await sync_stamp(db, principal.user_id)
        queries = []
        for kind, (model, fields) in ENTITIES.items():
            arguments: list[Any] = []
            for name in fields:
                arguments.extend((literal(name), getattr(model, name)))
            queries.append(
                select(
                    model.id.label("id"),
                    model.updated_at.label("updated_at"),
                    literal(kind).label("entity_type"),
                    func.jsonb_build_object(*arguments).label("payload"),
                ).where(model.user_id == principal.user_id)
            )
        merged = union_all(*queries).subquery()
        q = select(merged)
        if cursor:
            if cursor["kind"] == "position":
                q = q.where(
                    tuple_(merged.c.updated_at, merged.c.entity_type, merged.c.id)
                    > tuple_(cursor["t"], cursor["entity_type"], cursor["id"])
                )
            else:
                q = q.where(merged.c.updated_at > cursor["t"])
        rows = (
            (
                await db.execute(
                    q.order_by(
                        merged.c.updated_at, merged.c.entity_type, merged.c.id
                    ).limit(data.limit + 1)
                )
            )
            .mappings()
            .all()
        )
        more = len(rows) > data.limit
        rows = rows[: data.limit]
        result: dict[str, Any] = dict(
            updated_conversations=[],
            updated_highlights=[],
            updated_settings=None,
            total_items_in_page=len(rows),
            has_more=more,
        )
        for row in rows:
            key = {
                "conversation": "updated_conversations",
                "highlight": "updated_highlights",
                "settings": "updated_settings",
            }[row["entity_type"]]
            if row["entity_type"] == "settings":
                result[key] = row["payload"]
            else:
                result[key].append(row["payload"])
        if more:
            last = rows[-1]
            next_value = dict(
                v=1,
                kind="position",
                t=last["updated_at"].isoformat(),
                entity_type=last["entity_type"],
                id=str(last["id"]),
                anchor=anchor.isoformat(),
            )
        else:
            next_value = dict(
                v=1,
                kind="checkpoint",
                t=checkpoint.isoformat(),
                anchor=checkpoint.isoformat(),
            )
        result["next_cursor"] = encode_cursor(next_value)
        return {"data": result}


async def push(principal: Principal, data: SyncPushRequest) -> dict:
    """Apply a bounded batch atomically; never trust user IDs or server fields."""
    from pydantic import ValidationError

    async with transaction() as db:
        stamp = await sync_stamp(db, principal.user_id)
        changed = []
        for mutation in data.mutations:
            model, fields = ENTITIES[mutation.entity_type]
            row = await db.scalar(
                select(model)
                .where(
                    model.id == mutation.entity_id, model.user_id == principal.user_id
                )
                .execution_options(populate_existing=True)
            )
            if row is None:
                raise AppException(
                    400, "INVALID_SYNC_MUTATION", "Unknown or unowned sync entity"
                )
            if row.version != mutation.base_version or getattr(
                row, "is_deleted", False
            ):
                raise AppException(
                    409,
                    "SYNC_CONFLICT",
                    "Entity was changed or deleted",
                    server_record=public(row, fields),
                    client_version=mutation.base_version,
                )
            payload = mutation.payload.copy()
            if mutation.action == "delete":
                if mutation.entity_type == "settings" or payload:
                    raise AppException(
                        400, "INVALID_SYNC_MUTATION", "Invalid deletion payload"
                    )
                values: dict[str, Any] = {"is_deleted": True}
            else:
                allowed = {
                    "conversation": {"title"},
                    "highlight": {"user_note", "color"},
                    "settings": set(UserSettingUpdateRequest.model_fields)
                    - {"version"},
                }[mutation.entity_type]
                if not payload or set(payload) - allowed:
                    raise AppException(
                        400,
                        "INVALID_SYNC_MUTATION",
                        "Payload contains unsupported fields",
                    )
                try:
                    if mutation.entity_type == "settings":
                        checked = UserSettingUpdateRequest(
                            version=row.version, **payload
                        )
                        values = checked.model_dump(
                            exclude_unset=True, exclude={"version"}
                        )
                    elif mutation.entity_type == "highlight":
                        values = HighlightCreate(
                            page_url=row.page_url,
                            highlighted_text=row.highlighted_text,
                            user_note=payload.get("user_note", row.user_note),
                            color=payload.get("color", row.color),
                        ).model_dump(include=set(payload))
                    else:
                        if (
                            not isinstance(payload["title"], str)
                            or not 1 <= len(payload["title"]) <= 255
                        ):
                            raise ValueError()
                        validate_postgres_text(payload["title"])
                        values = payload
                except (ValidationError, ValueError, TypeError) as exc:
                    raise AppException(
                        400, "INVALID_SYNC_MUTATION", "Invalid entity fields"
                    ) from exc
            if mutation.entity_type == "settings":
                values = settings_values(row, values)
            values.update(version=model.version + 1, updated_at=stamp)
            updated = await db.scalar(
                update(model)
                .where(
                    model.id == row.id,
                    model.user_id == principal.user_id,
                    model.version == mutation.base_version,
                )
                .values(**values)
                .returning(model)
                .execution_options(populate_existing=True)
            )
            if updated is None:
                raise AppException(409, "SYNC_CONFLICT", "Concurrent entity update")
            changed.append(
                dict(entity_type=mutation.entity_type, record=public(updated, fields))
            )
        return {"data": {"mutations": changed}}
