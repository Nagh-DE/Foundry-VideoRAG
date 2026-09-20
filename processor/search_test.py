from __future__ import annotations

import argparse

from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import (
    VectorizableTextQuery,
)

from processor.settings import load_settings


def escape_odata(value: str) -> str:
    return value.replace("'", "''")


def search_video(
    question: str,
    tenant_id: str,
    video_id: str,
    top: int = 5,
) -> list[dict]:
    settings = load_settings()

    credential = DefaultAzureCredential(
        exclude_interactive_browser_credential=False
    )

    search_client = SearchClient(
        endpoint=settings.search_endpoint,
        index_name=settings.search_index_name,
        credential=credential,
    )

    filter_expression = (
        f"tenant_id eq "
        f"'{escape_odata(tenant_id)}' and "
        f"video_id eq "
        f"'{escape_odata(video_id)}' and "
        "is_active eq true"
    )

    vector_query = VectorizableTextQuery(
        text=question,
        k_nearest_neighbors=50,
        fields="content_vector",
    )

    results = search_client.search(
        search_text=question,
        vector_queries=[vector_query],
        vector_filter_mode="preFilter",
        filter=filter_expression,
        query_type="semantic",
        semantic_configuration_name=(
            settings.search_semantic_configuration_name
        ),
        select=[
            "id",
            "video_id",
            "scene_id",
            "chunk_title",
            "timestamp",
            "content",
            "transcript",
            "visual_summary",
            "ocr_text",
            "frame_blob_paths",
            "source_url",
        ],
        top=top,
        include_total_count=True,
    )

    print(
        f"Matching documents: "
        f"{results.get_count()}"
    )

    documents = []

    for result in results:
        document = dict(result)
        documents.append(document)

    return documents


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run a filtered hybrid/vector search "
            "against one indexed video."
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
        "--top",
        type=int,
        default=5,
    )

    arguments = parser.parse_args()

    documents = search_video(
        question=arguments.question,
        tenant_id=arguments.tenant_id,
        video_id=arguments.video_id,
        top=arguments.top,
    )

    if not documents:
        print("No matching evidence was found.")
        return

    for index, document in enumerate(
        documents,
        start=1,
    ):
        score = document.get(
            "@search.score"
        )
        reranker_score = document.get(
            "@search.reranker_score"
        )

        print("\n" + "=" * 72)
        print(f"Result {index}")
        print(f"ID: {document['id']}")
        print(
            f"Timestamp: "
            f"{document['timestamp']}"
        )
        print(
            f"Title: "
            f"{document['chunk_title']}"
        )
        print(f"Search score: {score}")
        print(
            f"Reranker score: "
            f"{reranker_score}"
        )

        frame_paths = document.get(
            "frame_blob_paths",
            [],
        )

        if frame_paths:
            print("Frames:")
            for frame_path in frame_paths:
                print(f"  - {frame_path}")

        content = document.get(
            "content",
            "",
        )

        print("\nEvidence:")
        print(content[:1500])


if __name__ == "__main__":
    main()