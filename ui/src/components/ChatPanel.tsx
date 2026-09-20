import { useState, useRef, useEffect } from 'react';
import type { Message, Citation } from '../types';
import TimestampChip from './TimestampChip';

interface MessageBubbleProps {
  msg: Message;
  onSeek: (citation: Citation) => void;
}

function MessageBubble({ msg, onSeek }: MessageBubbleProps) {
  const isUser = msg.role === 'user';
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[75%] px-4 py-3 rounded-2xl text-sm leading-relaxed ${
          isUser
            ? 'bg-gray-200 text-gray-900 rounded-br-sm'
            : 'bg-white border border-gray-200 text-gray-800 rounded-bl-sm shadow-sm'
        }`}
      >
        <p className="whitespace-pre-wrap break-words">{msg.content}</p>
        {msg.citations && msg.citations.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-2 pt-2 border-t border-gray-100">
            {msg.citations.map((c, i) => (
              <TimestampChip key={i} citation={c} onSeek={onSeek} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function ThinkingIndicator() {
  return (
    <div className="flex justify-start">
      <div className="bg-white border border-gray-200 rounded-2xl rounded-bl-sm px-4 py-3 shadow-sm">
        <div className="flex gap-1 items-center h-4">
          <span
            className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"
            style={{ animationDelay: '0ms' }}
          />
          <span
            className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"
            style={{ animationDelay: '150ms' }}
          />
          <span
            className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"
            style={{ animationDelay: '300ms' }}
          />
        </div>
      </div>
    </div>
  );
}

interface ChatPanelProps {
  messages: Message[];
  sending: boolean;
  sendError: string | null;
  onSend: (text: string) => void;
  onSeek: (citation: Citation) => void;
}

export default function ChatPanel({
  messages,
  sending,
  sendError,
  onSend,
  onSeek,
}: ChatPanelProps) {
  const [input, setInput] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, sending]);

  function submit() {
    const text = input.trim();
    if (!text || sending) return;
    setInput('');
    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
    onSend(text);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  function handleInput(e: React.FormEvent<HTMLTextAreaElement>) {
    const el = e.currentTarget;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 128)}px`;
  }

  return (
    <div className="flex flex-col h-full">
      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-3 bg-gray-50">
        {messages.length === 0 && !sending && (
          <div className="flex items-center justify-center h-full">
            <p className="text-sm text-gray-400 text-center">
              Ask a question about the video to get started.
            </p>
          </div>
        )}

        {messages.map((msg) => (
          <MessageBubble key={msg.id} msg={msg} onSeek={onSeek} />
        ))}

        {sending && <ThinkingIndicator />}

        {sendError && (
          <div className="flex justify-center">
            <p className="text-xs text-red-500 bg-red-50 border border-red-200 rounded-lg px-3 py-1.5">
              Error: {sendError}
            </p>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input bar */}
      <div className="flex-shrink-0 border-t border-gray-200 bg-white px-4 py-3">
        <div className="flex gap-2 items-end">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            onInput={handleInput}
            placeholder="Ask about the video… (Enter to send, Shift+Enter for new line)"
            rows={1}
            disabled={sending}
            className="flex-1 resize-none border border-gray-300 rounded-xl px-3.5 py-2.5 text-sm
                       focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent
                       disabled:bg-gray-50 disabled:text-gray-400
                       min-h-[42px] max-h-32 overflow-y-auto leading-relaxed"
          />
          <button
            onClick={submit}
            disabled={!input.trim() || sending}
            className="flex-shrink-0 px-4 py-2.5 bg-indigo-600 text-white rounded-xl text-sm
                       font-semibold hover:bg-indigo-700 active:bg-indigo-800
                       disabled:opacity-50 disabled:cursor-not-allowed transition-colors
                       min-h-[42px]"
          >
            Send
          </button>
        </div>
        <p className="text-xs text-gray-400 mt-1.5">
          Enter to send &middot; Shift+Enter for new line
        </p>
      </div>
    </div>
  );
}
