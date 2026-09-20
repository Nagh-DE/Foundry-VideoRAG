from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient
from azure.storage.blob import BlobServiceClient

from processor.settings import load_settings


def main() -> None:
    settings = load_settings()

    print("Loading Azure credentials...")
    credential = DefaultAzureCredential(
        exclude_interactive_browser_credential=False
    )

    management_token = credential.get_token(
        "https://management.azure.com/.default"
    )
    print(
        "Azure authentication: OK "
        f"(token expires at {management_token.expires_on})"
    )

    print("\nChecking Blob Storage...")
    blob_service = BlobServiceClient(
        account_url=settings.storage_account_url,
        credential=credential,
    )

    actual_containers = {
        container.name
        for container in blob_service.list_containers()
    }

    expected_containers = {
        settings.video_container,
        settings.frames_container,
        settings.metadata_container,
    }

    missing_containers = expected_containers - actual_containers
    if missing_containers:
        raise RuntimeError(
            "Missing Blob containers: "
            + ", ".join(sorted(missing_containers))
        )

    print(
        "Blob Storage: OK — "
        + ", ".join(sorted(expected_containers))
    )

    print("\nChecking Azure AI Search...")
    search_client = SearchClient(
        endpoint=settings.search_endpoint,
        index_name=settings.search_index_name,
        credential=credential,
    )

    document_count = search_client.get_document_count()
    print(
        f"Azure AI Search: OK — index "
        f"{settings.search_index_name!r}, "
        f"{document_count} documents"
    )

    print("\nChecking Microsoft Foundry and GPT-5.4...")
    project_client = AIProjectClient(
        endpoint=settings.foundry_project_endpoint,
        credential=credential,
    )
    openai_client = project_client.get_openai_client()

    response = openai_client.responses.create(
        model=settings.gpt_deployment_name,
        input="Reply with exactly: OK",
        max_output_tokens=32,
        store=False,
    )

    output = response.output_text.strip()
    if not output:
        raise RuntimeError("GPT-5.4 returned an empty response.")

    print(f"GPT-5.4: OK — response: {output!r}")

    print("\nChecking Azure Speech authentication...")
    speech_token = credential.get_token(
        "https://cognitiveservices.azure.com/.default"
    )
    print(
        "Azure Speech authentication: OK "
        f"(token expires at {speech_token.expires_on})"
    )

    print("\nAll processor connectivity checks passed.")


if __name__ == "__main__":
    main()