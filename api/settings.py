from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=[".env", ".env.generated"],
        extra="ignore",
        populate_by_name=True,
    )

    # Azure Identity — AZURE_WORKLOAD_IDENTITY_CLIENT_ID set by Deploy.ps1
    azure_client_id: str = Field(
        default="",
        validation_alias="AZURE_WORKLOAD_IDENTITY_CLIENT_ID",
    )

    # Storage
    azure_storage_account_url: str = ""

    # Foundry / Agent
    azure_foundry_project_endpoint: str = ""
    foundry_agent_name: str = Field(
        default="video-rag-agent",
        validation_alias="FOUNDRY_AGENT_NAME",
    )

    # Processor Job — env var names from .env
    processor_job_name: str = Field(
        default="",
        validation_alias="PROCESSOR_JOB_NAME",
    )
    azure_resource_group: str = Field(
        default="",
        validation_alias="RESOURCE_GROUP_NAME",
    )
    azure_subscription_id: str = Field(
        default="",
        validation_alias="AZURE_SUBSCRIPTION_ID",
    )

    # Blob containers
    video_container_name: str = "videos"
    frames_container_name: str = "frames"
    metadata_container_name: str = "metadata"

    # Table Storage
    conversations_table_name: str = "Conversations"

    # App config
    tenant_id: str = Field(default="dev-user", validation_alias="DEV_TENANT_ID")
    max_upload_mb: int = 500
    allowed_origins: str = "http://localhost:5173"

    @property
    def azure_table_account_url(self) -> str:
        return self.azure_storage_account_url.replace(
            ".blob.core.windows.net", ".table.core.windows.net"
        )

    @property
    def processor_job_container_name(self) -> str:
        return self.processor_job_name

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def storage_account_name(self) -> str:
        host = self.azure_storage_account_url.split("//")[-1]
        return host.split(".")[0]


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
