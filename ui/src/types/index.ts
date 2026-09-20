export interface VideoUploadResponse {
  video_id: string;
  filename: string;
  status: string;
}

export interface ProcessVideoResponse {
  execution_name: string;
  status: string;
}

export interface ProcessingStatus {
  video_id: string;
  status: 'uploaded' | 'processing' | 'ready' | 'failed';
  stage: string;
  progress: number;
  message?: string;
  updated_at?: string;
}

export interface VideoContent {
  url: string;
  expires_in_seconds: number;
}

export interface ConversationResponse {
  conversation_id: string;
  video_id: string;
  video_name: string;
  title: string;
  created_at: string;
  updated_at: string;
  last_message_preview?: string;
  message_count: number;
}

export interface Citation {
  timestamp: string;
  start_seconds: number;
  end_seconds: number;
}

export interface MessageResponse {
  conversation_id: string;
  response_id: string;
  answer: string;
  citations: Citation[];
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  citations?: Citation[];
  timestamp: string;
}
