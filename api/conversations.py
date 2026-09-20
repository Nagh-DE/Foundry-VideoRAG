from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from azure.core.exceptions import ResourceNotFoundError
from azure.data.tables import TableServiceClient, UpdateMode

from .models import ConversationResponse
from .settings import Settings


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _entity_to_response(entity: dict) -> ConversationResponse:
    return ConversationResponse(
        conversation_id=entity["RowKey"],
        video_id=entity.get("VideoId", ""),
        video_name=entity.get("VideoName", ""),
        title=entity.get("Title", "New conversation"),
        created_at=entity.get("CreatedAt", ""),
        updated_at=entity.get("UpdatedAt", ""),
        last_message_preview=entity.get("LastMessagePreview"),
        message_count=int(entity.get("MessageCount", 0)),
        status=entity.get("Status", "active"),
    )


def create_conversation(
    table_service: TableServiceClient,
    settings: Settings,
    video_id: str,
    video_name: str,
    foundry_conversation_id: str,
) -> ConversationResponse:
    table_client = table_service.get_table_client(settings.conversations_table_name)
    conversation_id = f"chat-{uuid.uuid4()}"
    now = _now_iso()

    entity = {
        "PartitionKey": settings.tenant_id,
        "RowKey": conversation_id,
        "FoundryConversationId": foundry_conversation_id,
        "VideoId": video_id,
        "VideoName": video_name,
        "Title": os.path.splitext(video_name)[0] if video_name else "New conversation",
        "CreatedAt": now,
        "UpdatedAt": now,
        "LastMessagePreview": None,
        "MessageCount": 0,
        "Status": "active",
    }

    table_client.create_entity(entity)
    return _entity_to_response(entity)


def list_conversations(
    table_service: TableServiceClient,
    settings: Settings,
) -> list[ConversationResponse]:
    table_client = table_service.get_table_client(settings.conversations_table_name)
    # Return only active conversations for the tenant, newest first
    filter_query = (
        f"PartitionKey eq '{settings.tenant_id}' and Status eq 'active'"
    )
    entities = list(table_client.query_entities(filter_query))
    # Sort by CreatedAt descending (newest first)
    entities.sort(key=lambda e: e.get("CreatedAt", ""), reverse=True)
    return [_entity_to_response(e) for e in entities]


def get_conversation(
    table_service: TableServiceClient,
    settings: Settings,
    conversation_id: str,
) -> ConversationResponse | None:
    table_client = table_service.get_table_client(settings.conversations_table_name)
    try:
        entity = table_client.get_entity(
            partition_key=settings.tenant_id,
            row_key=conversation_id,
        )
    except ResourceNotFoundError:
        return None

    if entity.get("Status") == "deleted":
        return None

    return _entity_to_response(entity)


def _get_raw_entity(
    table_service: TableServiceClient,
    settings: Settings,
    conversation_id: str,
) -> dict | None:
    """Return the raw table entity dict, or None if not found / deleted."""
    table_client = table_service.get_table_client(settings.conversations_table_name)
    try:
        entity = table_client.get_entity(
            partition_key=settings.tenant_id,
            row_key=conversation_id,
        )
        if entity.get("Status") == "deleted":
            return None
        return dict(entity)
    except ResourceNotFoundError:
        return None


def update_conversation_after_message(
    table_service: TableServiceClient,
    settings: Settings,
    conversation_id: str,
    last_message_preview: str,
    message_count: int,
) -> None:
    table_client = table_service.get_table_client(settings.conversations_table_name)
    try:
        entity = table_client.get_entity(
            partition_key=settings.tenant_id,
            row_key=conversation_id,
        )
    except ResourceNotFoundError:
        return

    entity["LastMessagePreview"] = last_message_preview[:120]
    entity["MessageCount"] = message_count
    entity["UpdatedAt"] = _now_iso()

    table_client.update_entity(entity, mode=UpdateMode.REPLACE)


def patch_conversation(
    table_service: TableServiceClient,
    settings: Settings,
    conversation_id: str,
    title: str,
) -> ConversationResponse:
    table_client = table_service.get_table_client(settings.conversations_table_name)
    entity = table_client.get_entity(
        partition_key=settings.tenant_id,
        row_key=conversation_id,
    )
    entity["Title"] = title
    entity["UpdatedAt"] = _now_iso()
    table_client.update_entity(entity, mode=UpdateMode.REPLACE)
    return _entity_to_response(dict(entity))


def delete_conversation(
    table_service: TableServiceClient,
    settings: Settings,
    conversation_id: str,
) -> None:
    table_client = table_service.get_table_client(settings.conversations_table_name)
    try:
        entity = table_client.get_entity(
            partition_key=settings.tenant_id,
            row_key=conversation_id,
        )
    except ResourceNotFoundError:
        return  # Already gone; treat as success

    entity["Status"] = "deleted"
    entity["UpdatedAt"] = _now_iso()
    table_client.update_entity(entity, mode=UpdateMode.REPLACE)
