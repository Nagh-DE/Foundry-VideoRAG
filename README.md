# Foundry VideoRAG

Upload any video — a carrier webinar, a Teams recording, a training session — and have a grounded, timestamped conversation with it.

Built on Azure AI Foundry, Azure AI Search, and Azure OpenAI.

---

## What it does

1. **Ingest** — Upload an MP4, paste a direct video URL, or submit a YouTube/Vimeo link.
2. **Process** — The pipeline extracts frames, transcribes audio, and generates AI visual descriptions for every frame using GPT-4V.
3. **Index** — A timeline is built from transcript + visual evidence, embedded with `text-embedding-3-small`, and indexed into Azure AI Search.
4. **Chat** — Ask natural-language questions and get grounded answers with exact `[HH:MM:SS]` timestamps pointing back to the video.

### Example

> *"What is the difference between first-party and third-party cyber coverage?"*
>
> **First-party coverage** applies to the insured's own costs — incident response, notification, business interruption, data restoration, and ransom [00:08:53–00:10:03]. **Third-party coverage** responds when outside parties bring claims — network security liability, privacy liability, regulatory exposure, and media liability [00:10:49–00:11:51].

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  INPUT                                                          │
│  MP4 Upload  │  Direct URL  │  YouTube / Video Link             │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│  Azure Blob Storage                                             │
│  videos/  │  frames/  │  metadata/                             │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│  Azure Container Apps Job  (Processor)                          │
│                                                                 │
│  1. Azure AI Speech  →  Transcription                           │
│  2. Azure OpenAI GPT  →  Frame Descriptions                  │
│  3. Timeline Builder  →  timeline_chunks.json                   │
│  4. text-embedding-3-small  →  Vector Embeddings                │
│  5. Azure AI Search  →  Indexed Timeline Chunks                 │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│  Azure AI Foundry Agent  (RAG + Answer Generation)              │
│  React UI  +  FastAPI  (Azure Container Apps)                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | React 18, React Router, TanStack Query, Tailwind CSS, Vite |
| API | Python 3.12, FastAPI, Uvicorn |
| Processor | Python 3.12, OpenCV, PyAV, Pillow, yt-dlp |
| AI — Vision | Azure OpenAI GPT-4V (`IMAGE_DETAIL=high`) |
| AI — Embeddings | Azure OpenAI `text-embedding-3-small` |
| AI — Transcription | Azure AI Speech Fast Transcription |
| AI — Agent | Azure AI Foundry Agent |
| Search | Azure AI Search (vector + semantic hybrid) |
| Storage | Azure Blob Storage |
| Compute | Azure Container Apps + Container Apps Job |
| Registry | Azure Container Registry |

---

## Repository structure

```
├── api/                  # FastAPI backend
│   ├── main.py           # Routes: upload, process, status, conversations, chat
│   ├── conversations.py  # Conversation and message management (Table Storage)
│   ├── storage.py        # Blob helpers, SAS URL generation
│   ├── processor_jobs.py # Container Apps Job trigger
│   └── requirements.txt
│
├── processor/            # Video processing pipeline (runs as Container Apps Job)
│   ├── job.py            # Entry point — download, process, upload metadata
│   ├── main.py           # Orchestrates the processing stages
│   ├── frame_extractor.py
│   ├── frame_describer.py
│   ├── timeline_builder.py
│   ├── index_writer.py   # Embeddings + Azure AI Search upload
│   └── requirements.txt
│
├── agent/                # Azure AI Foundry agent setup
│   ├── configure_agent.py
│   └── system_prompt.txt
│
├── ui/                   # React frontend
│   └── src/
│       ├── pages/        # HomePage, ProcessingPage, ChatPage
│       ├── components/   # Sidebar, UploadDropzone, VideoPlayer
│       └── services/     # api.ts — typed API client
│
├── Dockerfile            # API container image
└── processor/Dockerfile  # Processor container image
```

---

## Environment variables

### API (`.env` or Container App settings)

| Variable | Description |
|---|---|
| `AZURE_STORAGE_ACCOUNT_URL` | Blob storage endpoint |
| `VIDEO_CONTAINER_NAME` | Container for source videos |
| `FRAMES_CONTAINER_NAME` | Container for extracted frames |
| `METADATA_CONTAINER_NAME` | Container for processing status and timeline JSON |
| `AZURE_SEARCH_ENDPOINT` | Azure AI Search endpoint |
| `AZURE_SEARCH_INDEX_NAME` | Index name |
| `AZURE_FOUNDRY_PROJECT_ENDPOINT` | AI Foundry project endpoint |
| `AZURE_OPENAI_DEPLOYMENT` | GPT deployment name |
| `FOUNDRY_AGENT_NAME` | AI Foundry agent name |
| `PROCESSOR_JOB_NAME` | Container Apps Job name |
| `AZURE_SUBSCRIPTION_ID` | Azure subscription ID |
| `RESOURCE_GROUP_NAME` | Resource group |

### Processor (Container Apps Job environment)

| Variable | Default | Description |
|---|---|---|
| `FRAME_INTERVAL_SECONDS` | `3` | Extract one frame every N seconds |
| `MAX_FRAMES` | `120` | Cap on total frames per video |
| `IMAGE_DETAIL` | `high` | GPT-4V detail level (`low` or `high`) |
| `VIDEO_ID` | — | Set per-execution by the API |
| `VIDEO_BLOB_NAME` | — | Set per-execution by the API |

---

## Local development

### Prerequisites

- Python 3.12+
- Node.js 18+
- [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) (`az login`)
- ffmpeg (for local yt-dlp merging)

### API

```bash
cd api
pip install -r requirements.txt
cp ../.env.example .env   # fill in your values
uvicorn main:app --reload --port 8000
```

### UI

```bash
cd ui
npm install
npm run dev               # starts on http://localhost:5173
```

The UI proxies `/api` to `http://localhost:8000` in dev mode.

### Processor (local test run)

```bash
cd processor
pip install -r requirements.txt
python -m processor.main \
  --video path/to/video.mp4 \
  --video-id test-001 \
  --frame-interval 10 \
  --max-frames 30
```

---

## Deployment

The project deploys to Azure Container Apps using the provided deploy script.

```bash
# Build and push API image
az acr build --registry <your-acr> --image video-rag-api:dev --file Dockerfile .

# Build and push processor image
az acr build --registry <your-acr> --image video-rag-processor:dev --file processor/Dockerfile .
```

The processor image is used by the Container Apps Job; the API image runs the web service.

---

## Cost notes

Azure AI Search is the only fixed-cost service (~$73/month for Basic tier). All other services are consumption-based and cost nothing when idle.

To pause costs between demos, delete the search service after use — all video files, frames, transcripts, and timeline JSON remain in Blob Storage. Re-indexing a previously processed video takes ~2 minutes.

---

## Use cases

- **Insurance brokers** — search carrier webinars and product training recordings
- **Enterprise teams** — make Teams meeting recordings queryable
- **Training & enablement** — turn recorded onboarding sessions into a knowledge base
- **Compliance** — retrieve specific statements from recorded client calls with timestamp evidence
