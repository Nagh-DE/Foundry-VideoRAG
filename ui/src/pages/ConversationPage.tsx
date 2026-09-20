import { useState, useRef, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { getConversation, sendMessage } from '../services/api';
import { useVideoSas } from '../hooks/useVideoSas';
import { CONVERSATIONS_KEY } from '../hooks/useConversations';
import Sidebar from '../components/Sidebar';
import VideoPlayer, { type VideoPlayerHandle } from '../components/VideoPlayer';
import ChatPanel from '../components/ChatPanel';
import type { Message, Citation } from '../types';

export default function ConversationPage() {
  const { conversationId } = useParams<{ conversationId: string }>();
  const qc = useQueryClient();
  const videoRef = useRef<VideoPlayerHandle>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);

  // Reset local message state whenever the conversation changes
  useEffect(() => {
    setMessages([]);
    setSendError(null);
    setSending(false);
  }, [conversationId]);

  const { data: conversation, error: convError } = useQuery({
    queryKey: ['conversation', conversationId],
    queryFn: () => getConversation(conversationId!),
    enabled: !!conversationId,
  });

  const { sasUrl, error: sasError } = useVideoSas(conversation?.video_id);

  async function handleSend(text: string) {
    if (!conversationId || !text.trim() || sending) return;

    setSending(true);
    setSendError(null);

    // Optimistically add user message to local state
    const userMsg: Message = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: text,
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);

    try {
      const resp = await sendMessage(conversationId, text);
      const assistantMsg: Message = {
        id: resp.response_id,
        role: 'assistant',
        content: resp.answer,
        citations: resp.citations,
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, assistantMsg]);
      // Refresh sidebar so last_message_preview updates
      void qc.invalidateQueries({ queryKey: CONVERSATIONS_KEY });
    } catch (e) {
      setSendError((e as Error).message);
    } finally {
      setSending(false);
    }
  }

  function handleSeek(citation: Citation) {
    videoRef.current?.seekTo(citation.start_seconds);
  }

  const videoAreaError = convError
    ? 'Could not load conversation.'
    : sasError
    ? `Could not load video: ${sasError}`
    : null;

  return (
    <div className="flex h-screen overflow-hidden bg-white">
      {/* Sidebar */}
      <Sidebar
        currentConversationId={conversationId}
        currentVideoId={conversation?.video_id}
      />

      {/* Main content */}
      <div className="flex flex-col flex-1 overflow-hidden">
        {/* Compact video player strip */}
        <div className="bg-gray-900 flex-shrink-0 p-2">
          {videoAreaError ? (
            <div className="h-[220px] flex items-center justify-center">
              <p className="text-red-400 text-sm">{videoAreaError}</p>
            </div>
          ) : sasUrl ? (
            <VideoPlayer ref={videoRef} src={sasUrl} compact />
          ) : (
            <div className="h-[220px] flex flex-col items-center justify-center gap-2">
              <div className="w-5 h-5 border-2 border-gray-500 border-t-gray-300 rounded-full animate-spin" />
              <p className="text-gray-500 text-sm">Loading video&hellip;</p>
            </div>
          )}
        </div>

        {/* Chat panel fills remaining space */}
        <div className="flex-1 overflow-hidden">
          <ChatPanel
            messages={messages}
            sending={sending}
            sendError={sendError}
            onSend={(text) => void handleSend(text)}
            onSeek={handleSeek}
          />
        </div>
      </div>
    </div>
  );
}
