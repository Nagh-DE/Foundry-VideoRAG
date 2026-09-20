from __future__ import annotations

from typing import Optional
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Video upload / ingest
# ---------------------------------------------------------------------------

class VideoUploadResponse(BaseModel):
    video_id: str
    filename: str
    status: str


class VideoFromUrlRequest(BaseModel):
    url: str


class VideoFromUrlResponse(BaseModel):
    video_id: str
    filename: str
    status: str


# ---------------------------------------------------------------------------
# Processing status
# ---------------------------------------------------------------------------

class ProcessingStatusResponse(BaseModel):
    video_id: str
    status: str
    stage: str
    progress: int
    message: Optional[str] = None
    updated_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Video metadata
# ---------------------------------------------------------------------------

class VideoMetadata(BaseModel):
    video_id: str
    filename: str
    status: str
    stage: Optional[str] = None
    progress: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Processor job
# ---------------------------------------------------------------------------

class ProcessJobResponse(BaseModel):
    execution_name: str
    status: str


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------

class ConversationCreate(BaseModel):
    pass  # No body fields required — video_id comes from URL


class ConversationResponse(BaseModel):
    conversation_id: str
    video_id: str
    video_name: str
    title: str
    created_at: str
    updated_at: str
    last_message_preview: Optional[str] = None
    message_count: int = 0
    status: str = "active"


class ConversationListResponse(BaseModel):
    conversations: list[ConversationResponse]
    total: int


class PatchConversationRequest(BaseModel):
    title: str


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

class MessageRequest(BaseModel):
    message: str


class CitationModel(BaseModel):
    timestamp: str
    start_seconds: int
    end_seconds: int


class MessageResponse(BaseModel):
    conversation_id: str
    answer: str
    citations: list[CitationModel]
    response_id: str


# ---------------------------------------------------------------------------
# Video SAS URL
# ---------------------------------------------------------------------------

class VideoContentResponse(BaseModel):
    url: str
    expires_in_seconds: int = 300
