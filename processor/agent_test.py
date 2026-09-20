from __future__ import annotations

import argparse
import json
from pathlib import Path

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

from processor.settings import load_settings


def ask_agent(
    question: str,
    tenant_id: str,
    video_id: str,
    conversation_id: str | None = None,
) -> dict:
    settings = load_settings()

    credential = DefaultAzureCredential(
        exclude_interactive_browser_credential=False
    )

    project_client = AIProjectClient(
        endpoint=settings.foundry_project_endpoint,
        credential=credential,
    )
    openai_client = (
        project_client.get_openai_client()
    )

    if conversation_id is None:
        conversation = (
            openai_client.conversations.create()
        )
        conversation_id = conversation.id

        print(
            "Created Foundry conversation: "
            f"{conversation_id}"
        )
    else:
        print(
            "Using Foundry conversation: "
            f"{conversation_id}"
        )

    print(
        f"Asking agent {settings.foundry_agent_name!r}..."
    )

    response = openai_client.responses.create(
        conversation=conversation_id,
        input=question,
        tool_choice="required",
        extra_body={
            "agent_reference": {
                "name": (
                    settings.foundry_agent_name
                ),
                "type": "agent_reference",
            },
            "structured_inputs": {
                "tenant_id": tenant_id,
                "video_id": video_id,
            },
        },
    )

    answer = response.output_text.strip()

    if not answer:
        raise RuntimeError(
            "The Foundry agent returned an empty answer."
        )

    return {
        "conversation_id": conversation_id,
        "response_id": response.id,
        "tenant_id": tenant_id,
        "video_id": video_id,
        "question": question,
        "answer": answer,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Ask the Foundry Video RAG agent "
            "a question about one video."
        )
    )
    parser.add_argument(
        "--question",
        required=True,
    )
    parser.add_argument(
        "--tenant-id",
        required=True,
    )
    parser.add_argument(
        "--video-id",
        required=True,
    )
    parser.add_argument(
        "--conversation-id",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "artifacts/agent_test_result.json"
        ),
    )

    arguments = parser.parse_args()

    result = ask_agent(
        question=arguments.question,
        tenant_id=arguments.tenant_id,
        video_id=arguments.video_id,
        conversation_id=(
            arguments.conversation_id
        ),
    )

    arguments.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    arguments.output.write_text(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print("\nAgent answer:\n")
    print(result["answer"])

    print(
        "\nConversation ID: "
        f"{result['conversation_id']}"
    )
    print(
        f"Saved result: "
        f"{arguments.output.resolve()}"
    )


if __name__ == "__main__":
    main()