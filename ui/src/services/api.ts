import type {
  VideoUploadResponse,
  ProcessVideoResponse,
  ProcessingStatus,
  VideoContent,
  ConversationResponse,
  MessageResponse,
} from '../types';

const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '';

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(text || `HTTP ${res.status}`);
  }
  if (res.status === 204) return undefined as unknown as T;
  return res.json() as Promise<T>;
}

export async function uploadVideo(
  file: File,
  onProgress?: (pct: number) => void
): Promise<VideoUploadResponse> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const form = new FormData();
    form.append('file', file);

    xhr.open('POST', `${API_BASE}/api/videos/upload`);

    if (onProgress) {
      xhr.upload.addEventListener('progress', (e) => {
        if (e.lengthComputable) {
          onProgress(Math.round((e.loaded / e.total) * 100));
        }
      });
    }

    xhr.addEventListener('load', () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText) as VideoUploadResponse);
        } catch {
          reject(new Error('Invalid JSON response from server'));
        }
      } else {
        reject(new Error(xhr.responseText || `Upload failed: HTTP ${xhr.status}`));
      }
    });

    xhr.addEventListener('error', () => reject(new Error('Network error during upload')));
    xhr.addEventListener('abort', () => reject(new Error('Upload aborted')));

    xhr.send(form);
  });
}

export async function uploadVideoFromUrl(url: string): Promise<VideoUploadResponse> {
  const res = await fetch(`${API_BASE}/api/videos/from-url`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  });
  return handleResponse<VideoUploadResponse>(res);
}

export async function submitVideoLink(url: string): Promise<VideoUploadResponse> {
  const res = await fetch(`${API_BASE}/api/videos/from-link`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  });
  return handleResponse<VideoUploadResponse>(res);
}

export async function processVideo(videoId: string): Promise<ProcessVideoResponse> {
  const res = await fetch(`${API_BASE}/api/videos/${videoId}/process`, {
    method: 'POST',
  });
  return handleResponse<ProcessVideoResponse>(res);
}

export async function getProcessingStatus(videoId: string): Promise<ProcessingStatus> {
  const res = await fetch(`${API_BASE}/api/videos/${videoId}/status`);
  return handleResponse<ProcessingStatus>(res);
}

export async function getVideoContent(videoId: string): Promise<VideoContent> {
  const res = await fetch(`${API_BASE}/api/videos/${videoId}/content`);
  return handleResponse<VideoContent>(res);
}

export async function createConversation(videoId: string): Promise<ConversationResponse> {
  const res = await fetch(`${API_BASE}/api/videos/${videoId}/conversations`, {
    method: 'POST',
  });
  return handleResponse<ConversationResponse>(res);
}

export async function listConversations(): Promise<{ conversations: ConversationResponse[] }> {
  const res = await fetch(`${API_BASE}/api/conversations`);
  return handleResponse<{ conversations: ConversationResponse[] }>(res);
}

export async function getConversation(conversationId: string): Promise<ConversationResponse> {
  const res = await fetch(`${API_BASE}/api/conversations/${conversationId}`);
  return handleResponse<ConversationResponse>(res);
}

export async function sendMessage(
  conversationId: string,
  message: string
): Promise<MessageResponse> {
  const res = await fetch(`${API_BASE}/api/conversations/${conversationId}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  });
  return handleResponse<MessageResponse>(res);
}

export async function renameConversation(
  conversationId: string,
  title: string
): Promise<ConversationResponse> {
  const res = await fetch(`${API_BASE}/api/conversations/${conversationId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  });
  return handleResponse<ConversationResponse>(res);
}

export async function deleteConversation(conversationId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/conversations/${conversationId}`, {
    method: 'DELETE',
  });
  return handleResponse<void>(res);
}
