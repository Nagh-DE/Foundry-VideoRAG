import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]

load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / ".env.generated", override=True)


def required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(
            f"Required environment variable {name!r} is missing. "
            "Check .env and .env.generated."
        )
    return value


@dataclass(frozen=True)
class Settings:
    storage_account_url: str
    video_container: str
    frames_container: str
    metadata_container: str
    openai_base_url: str

    search_endpoint: str
    search_index_name: str

    foundry_project_endpoint: str
    gpt_deployment_name: str
    embedding_deployment_name: str

    speech_endpoint: str
    speech_api_version: str

    tenant_id: str
    embedding_dimensions: int
    search_semantic_configuration_name: str
    foundry_agent_name: str


def load_settings() -> Settings:
    return Settings(
        storage_account_url=required("AZURE_STORAGE_ACCOUNT_URL"),
        video_container=required("VIDEO_CONTAINER_NAME"),
        frames_container=required("FRAMES_CONTAINER_NAME"),
        metadata_container=required("METADATA_CONTAINER_NAME"),
        search_endpoint=required("AZURE_SEARCH_ENDPOINT"),
        search_index_name=required("AZURE_SEARCH_INDEX_NAME"),
        foundry_project_endpoint=required(
            "AZURE_FOUNDRY_PROJECT_ENDPOINT"
        ),
        gpt_deployment_name=required("GPT_DEPLOYMENT_NAME"),
        embedding_deployment_name=required(
            "EMBEDDING_DEPLOYMENT_NAME"
        ),
        speech_endpoint=required("AZURE_SPEECH_ENDPOINT"),
        speech_api_version=os.getenv(
            "SPEECH_API_VERSION",
            "2025-10-15",
        ),
        tenant_id=os.getenv("DEV_TENANT_ID", "dev-user"),
        embedding_dimensions=int(
            required("EMBEDDING_DIMENSIONS")
        ),
        openai_base_url=required(
            "AZURE_OPENAI_BASE_URL"
        ),
        search_semantic_configuration_name=required(
            "SEARCH_SEMANTIC_CONFIGURATION_NAME"
        ),
        foundry_agent_name=required(
            "FOUNDRY_AGENT_NAME"
        ),
    )