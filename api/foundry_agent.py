from __future__ import annotations

import re
from typing import Any

from azure.ai.projects import AIProjectClient

from .settings import Settings

# Module-level singleton for the OpenAI client
_openai_client = None


def get_openai_client(settings: Settings, credential: Any):
    """Return a cached OpenAI client backed by the Foundry project."""
    global _openai_client
    if _openai_client is None:
        project_client = AIProjectClient(
            endpoint=settings.azure_foundry_project_endpoint,
            credential=credential,
        )
        _openai_client = project_client.get_openai_client()
    return _openai_client


def create_foundry_conversation(openai_client) -> str:
    """Create a new Foundry conversation and return its ID."""
    conversation = openai_client.conversations.create()
    return conversation.id


def parse_citations(text: str) -> list[dict]:
    """
    Parse timestamp citations of the form [HH:MM:SS] or [HH:MM:SS-HH:MM:SS]
    from agent response text.

    Returns a list of dicts with keys:
        timestamp     – the full citation string (e.g. "00:02:15" or "00:02:15-00:03:30")
        start_seconds – start time in seconds
        end_seconds   – end time in seconds (same as start for point citations)
    """
    pattern = r'\[(\d{2}:\d{2}:\d{2})(?:-(\d{2}:\d{2}:\d{2}))?\]'
    citations: list[dict] = []
    seen: set[str] = set()

    for match in re.finditer(pattern, text):
        start_str = match.group(1)
        end_str = match.group(2)

        key = f"{start_str}-{end_str or start_str}"
        if key in seen:
            continue
        seen.add(key)

        start_seconds = _hhmmss_to_seconds(start_str)
        end_seconds = _hhmmss_to_seconds(end_str) if end_str else start_seconds

        timestamp = start_str if end_str is None else f"{start_str}-{end_str}"
        citations.append(
            {
                "timestamp": timestamp,
                "start_seconds": start_seconds,
                "end_seconds": end_seconds,
            }
        )

    return citations


def _hhmmss_to_seconds(hhmmss: str) -> int:
    """Convert HH:MM:SS to total seconds."""
    parts = hhmmss.split(":")
    hours, minutes, seconds = int(parts[0]), int(parts[1]), int(parts[2])
    return hours * 3600 + minutes * 60 + seconds


def send_message(
    openai_client,
    foundry_conversation_id: str,
    question: str,
    tenant_id: str,
    video_id: str,
    agent_name: str,
) -> dict:
    """
    Send a user message to the Foundry agent and return the answer with citations.

    Returns:
        {
            "answer": str,
            "citations": list[dict],
            "response_id": str,
        }
    """
    response = openai_client.responses.create(
        conversation=foundry_conversation_id,
        input=question,
        tool_choice="required",
        extra_body={
            "agent_reference": {
                "name": agent_name,
                "type": "agent_reference",
            },
            "structured_inputs": {
                "tenant_id": tenant_id,
                "video_id": video_id,
            },
        },
    )

    answer = response.output_text.strip() if response.output_text else ""
    citations = parse_citations(answer)

    return {
        "answer": answer,
        "citations": citations,
        "response_id": response.id,
    }
