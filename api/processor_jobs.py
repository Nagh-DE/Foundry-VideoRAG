from __future__ import annotations

import time
from typing import Any

import httpx

_MGMT_SCOPE = "https://management.azure.com/.default"
_API_VERSION = "2024-03-01"


def _bearer(credential: Any) -> str:
    return credential.get_token(_MGMT_SCOPE).token


def _job_url(settings: Any, suffix: str = "") -> str:
    return (
        f"https://management.azure.com"
        f"/subscriptions/{settings.azure_subscription_id}"
        f"/resourceGroups/{settings.azure_resource_group}"
        f"/providers/Microsoft.App/jobs/{settings.processor_job_name}"
        f"{suffix}?api-version={_API_VERSION}"
    )


def _get_base_container(credential: Any, settings: Any) -> dict:
    """Fetch the container definition (image + env vars) from the job template."""
    hdrs = {"Authorization": f"Bearer {_bearer(credential)}"}
    resp = httpx.get(_job_url(settings), headers=hdrs, timeout=30)
    resp.raise_for_status()
    containers = resp.json().get("properties", {}).get("template", {}).get("containers", [])
    for c in containers:
        if c.get("name") == settings.processor_job_container_name:
            return c
    return containers[0] if containers else {}


def start_processor_job(
    credential: Any,
    settings: Any,
    video_id: str,
    tenant_id: str,
    blob_name: str,
) -> str:
    base = _get_base_container(credential, settings)

    # Azure replaces (not merges) env vars when a container override is provided,
    # so we must send the full env set with per-execution values merged in.
    env_map: dict[str, str] = {}
    for e in base.get("env", []):
        if "value" in e:
            env_map[e["name"]] = e["value"]
        # preserve secretRef entries as-is by keeping them in a separate list
    env_map["VIDEO_ID"] = video_id
    env_map["TENANT_ID"] = tenant_id
    env_map["VIDEO_BLOB_NAME"] = blob_name

    env_list = [{"name": k, "value": v} for k, v in env_map.items()]
    # Re-add any secretRef entries (not overrideable per-execution)
    for e in base.get("env", []):
        if "secretRef" in e and e["name"] not in env_map:
            env_list.append(e)

    body = {
        "containers": [
            {
                "name": base.get("name"),
                "image": base.get("image"),
                "env": env_list,
            }
        ]
    }

    token = _bearer(credential)
    hdrs = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    resp = httpx.post(_job_url(settings, "/start"), json=body, headers=hdrs, timeout=30)

    if resp.status_code == 200:
        return resp.json().get("name", "")

    if resp.status_code == 202:
        poll_url = resp.headers.get("location") or resp.headers.get("azure-asyncoperation", "")
        poll_hdrs = {"Authorization": f"Bearer {_bearer(credential)}"}
        for _ in range(15):
            time.sleep(2)
            pr = httpx.get(poll_url, headers=poll_hdrs, timeout=30)
            if pr.status_code == 200:
                data = pr.json()
                name = data.get("name", "")
                if name:
                    return name
                op_status = data.get("status", "InProgress")
                if op_status == "Succeeded":
                    return data.get("properties", {}).get("name", "")
                if op_status in ("Failed", "Canceled"):
                    raise RuntimeError(f"Job start failed: {data}")
        return ""

    resp.raise_for_status()
    return ""


def get_job_execution_status(
    credential: Any,
    settings: Any,
    execution_name: str,
) -> str:
    try:
        hdrs = {"Authorization": f"Bearer {_bearer(credential)}"}
        resp = httpx.get(
            _job_url(settings, f"/executions/{execution_name}"),
            headers=hdrs,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("properties", {}).get("status", "Unknown")
    except Exception:
        return "Unknown"
