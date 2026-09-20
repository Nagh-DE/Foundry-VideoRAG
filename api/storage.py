from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

from azure.core.exceptions import ResourceNotFoundError
from azure.data.tables import TableServiceClient
from azure.storage.blob import (
    BlobServiceClient,
    BlobSasPermissions,
    UserDelegationKey,
    generate_blob_sas,
)


# ---------------------------------------------------------------------------
# Client factories
# ---------------------------------------------------------------------------

def get_blob_service_client(credential: Any, storage_account_url: str) -> BlobServiceClient:
    """Return a BlobServiceClient authenticated via the given credential."""
    return BlobServiceClient(account_url=storage_account_url, credential=credential)


def get_table_service_client(credential: Any, table_account_url: str) -> TableServiceClient:
    """Return a TableServiceClient authenticated via the given credential."""
    return TableServiceClient(endpoint=table_account_url, credential=credential)


# ---------------------------------------------------------------------------
# Blob helpers
# ---------------------------------------------------------------------------

def upload_blob_stream(
    blob_service: BlobServiceClient,
    container: str,
    blob_name: str,
    stream,
    content_type: str = "video/mp4",
    chunk_size: int = 4 * 1024 * 1024,  # 4 MB
) -> None:
    """Stream-upload a file-like object to blob storage in chunks."""
    blob_client = blob_service.get_blob_client(container=container, blob=blob_name)
    from azure.storage.blob import ContentSettings
    blob_client.upload_blob(
        stream,
        overwrite=True,
        content_settings=ContentSettings(content_type=content_type),
        max_concurrency=4,
    )


def upload_blob_bytes(
    blob_service: BlobServiceClient,
    container: str,
    blob_name: str,
    data: bytes,
    content_type: str = "application/json",
) -> None:
    """Upload raw bytes to blob storage."""
    blob_client = blob_service.get_blob_client(container=container, blob=blob_name)
    from azure.storage.blob import ContentSettings
    blob_client.upload_blob(
        data,
        overwrite=True,
        content_settings=ContentSettings(content_type=content_type),
    )


def download_blob_json(
    blob_service: BlobServiceClient,
    container: str,
    blob_name: str,
) -> dict | None:
    """Download a blob and parse as JSON. Returns None if the blob does not exist."""
    try:
        blob_client = blob_service.get_blob_client(container=container, blob=blob_name)
        data = blob_client.download_blob().readall()
        return json.loads(data)
    except ResourceNotFoundError:
        return None


# ---------------------------------------------------------------------------
# SAS URL generation
# ---------------------------------------------------------------------------

def generate_video_sas_url(
    storage_account_url: str,
    account_name: str,
    container: str,
    blob_name: str,
    credential: Any,
    expiry_minutes: int = 5,
) -> str:
    """
    Generate a short-lived SAS URL for the given blob using a user delegation key.
    The credential must be a TokenCredential (e.g. DefaultAzureCredential).
    """
    blob_service = BlobServiceClient(account_url=storage_account_url, credential=credential)

    now = datetime.now(timezone.utc)
    expiry = now + timedelta(minutes=expiry_minutes)

    # Obtain user delegation key (valid for the requested window)
    udk: UserDelegationKey = blob_service.get_user_delegation_key(
        key_start_time=now,
        key_expiry_time=expiry,
    )

    sas_token = generate_blob_sas(
        account_name=account_name,
        container_name=container,
        blob_name=blob_name,
        user_delegation_key=udk,
        permission=BlobSasPermissions(read=True),
        expiry=expiry,
    )

    encoded_blob = quote(blob_name, safe="/")
    return f"{storage_account_url}/{container}/{encoded_blob}?{sas_token}"
