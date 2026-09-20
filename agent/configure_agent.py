import json
import os
from pathlib import Path

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    AISearchIndexResource,
    AzureAISearchQueryType,
    AzureAISearchTool,
    AzureAISearchToolResource,
    PromptAgentDefinition,
    StructuredInputDefinition,
)
from azure.identity import DefaultAzureCredential


def required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Required environment variable {name!r} is missing.")
    return value


project_endpoint = required("AZURE_FOUNDRY_PROJECT_ENDPOINT")
connection_name = required("SEARCH_CONNECTION_NAME")
index_name = required("SEARCH_INDEX_NAME")
deployment_name = required("GPT_DEPLOYMENT_NAME")
agent_name = required("FOUNDRY_AGENT_NAME")

prompt_path = Path(__file__).with_name("system_prompt.txt")
instructions = prompt_path.read_text(encoding="utf-8").strip()

project = AIProjectClient(
    endpoint=project_endpoint,
    credential=DefaultAzureCredential(),
)
connection = project.connections.get(connection_name)

video_filter = (
    "tenant_id eq '{{tenant_id}}' and "
    "video_id eq '{{video_id}}' and "
    "is_active eq true"
)
search_tool = AzureAISearchTool(
    azure_ai_search=AzureAISearchToolResource(
        indexes=[
            AISearchIndexResource(
                project_connection_id=connection.id,
                index_name=index_name,
                query_type=AzureAISearchQueryType.VECTOR_SEMANTIC_HYBRID,
                filter=video_filter,
                top_k=8,
            )
        ]
    )
)

agent = project.agents.create_version(
    agent_name=agent_name,
    definition=PromptAgentDefinition(
        model=deployment_name,
        instructions=instructions,
        tools=[search_tool],
        structured_inputs={
            "tenant_id": StructuredInputDefinition(
                description="Authorized tenant identifier.",
                required=True,
                schema={"type": "string"},
            ),
            "video_id": StructuredInputDefinition(
                description="Authorized video identifier.",
                required=True,
                schema={"type": "string"},
            ),
        },
    ),
    description="Timestamped video question-answering development agent.",
)

output = {
    "name": agent.name,
    "version": agent.version,
    "id": getattr(agent, "id", None),
}
output_path = Path(__file__).parents[1] / "agent-output.json"
output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
print(json.dumps(output, indent=2))
