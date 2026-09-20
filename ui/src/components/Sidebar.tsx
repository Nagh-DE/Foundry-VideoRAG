import { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import {
  useConversations,
  useRenameConversation,
  useDeleteConversation,
} from '../hooks/useConversations';
import type { ConversationResponse } from '../types';

interface SidebarProps {
  currentConversationId?: string;
  currentVideoId?: string;
}

interface ConversationItemProps {
  conv: ConversationResponse;
  isActive: boolean;
  onDelete: () => void;
  onRename: (title: string) => void;
}

function ConversationItem({ conv, isActive, onDelete, onRename }: ConversationItemProps) {
  const navigate = useNavigate();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(conv.title);

  // Keep draft in sync if parent data refreshes
  useEffect(() => {
    if (!editing) setDraft(conv.title);
  }, [conv.title, editing]);

  function handleBlur() {
    setEditing(false);
    const trimmed = draft.trim();
    if (trimmed && trimmed !== conv.title) {
      onRename(trimmed);
    } else {
      setDraft(conv.title);
    }
  }

  function handleItemClick() {
    if (!editing) {
      navigate(`/chats/${conv.conversation_id}`);
    }
  }

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={handleItemClick}
      onKeyDown={(e) => { if (e.key === 'Enter') handleItemClick(); }}
      className={`group flex items-start gap-2 px-3 py-2.5 rounded-lg cursor-pointer
                  transition-colors select-none ${
                    isActive ? 'bg-gray-700' : 'hover:bg-gray-800'
                  }`}
    >
      <div className="flex-1 min-w-0">
        {editing ? (
          <input
            autoFocus
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={handleBlur}
            onKeyDown={(e) => {
              if (e.key === 'Enter') e.currentTarget.blur();
              if (e.key === 'Escape') { setDraft(conv.title); setEditing(false); }
            }}
            onClick={(e) => e.stopPropagation()}
            className="w-full bg-gray-600 text-white text-sm rounded px-1.5 py-0.5
                       outline-none focus:ring-1 focus:ring-indigo-400"
          />
        ) : (
          <p
            className="text-sm font-medium text-gray-100 truncate"
            title={conv.title}
            onDoubleClick={(e) => { e.stopPropagation(); setEditing(true); }}
          >
            {conv.title}
          </p>
        )}
        <p className="text-xs text-gray-400 truncate mt-0.5" title={conv.video_name}>
          {conv.video_name}
        </p>
        {conv.last_message_preview && (
          <p className="text-xs text-gray-500 truncate mt-0.5">
            {conv.last_message_preview}
          </p>
        )}
      </div>

      <button
        onClick={(e) => { e.stopPropagation(); onDelete(); }}
        className="flex-shrink-0 text-gray-600 hover:text-red-400 transition-colors
                   leading-none text-xl w-5 h-5 flex items-center justify-center rounded"
        title="Delete conversation"
        aria-label="Delete conversation"
      >
        &times;
      </button>
    </div>
  );
}

export default function Sidebar({ currentConversationId, currentVideoId }: SidebarProps) {
  const navigate = useNavigate();
  const { data: conversations, isLoading } = useConversations();
  const rename = useRenameConversation();
  const del = useDeleteConversation();

  async function handleDelete(convId: string) {
    try {
      await del.mutateAsync(convId);
      if (convId === currentConversationId) {
        navigate('/');
      }
    } catch {
      // Silently ignore — mutation error can be observed via del.error if needed
    }
  }

  return (
    <aside className="w-64 flex-shrink-0 bg-gray-900 flex flex-col h-full overflow-hidden border-r border-gray-800">
      {/* Brand */}
      <div className="px-4 pt-5 pb-3 flex-shrink-0">
        <Link to="/" className="block">
          <h1 className="text-base font-bold text-white tracking-tight">Video RAG</h1>
        </Link>
      </div>

      {/* New chat / New video button */}
      <div className="px-3 mb-3 flex-shrink-0">
        {currentVideoId ? (
          <Link
            to={`/videos/${currentVideoId}`}
            className="flex items-center gap-1.5 w-full px-3 py-2 bg-indigo-600 hover:bg-indigo-700
                       text-white text-sm font-medium rounded-lg transition-colors"
          >
            <span className="text-base leading-none font-bold">+</span>
            New chat
          </Link>
        ) : (
          <Link
            to="/"
            className="flex items-center gap-1.5 w-full px-3 py-2 bg-indigo-600 hover:bg-indigo-700
                       text-white text-sm font-medium rounded-lg transition-colors"
          >
            <span className="text-base leading-none font-bold">+</span>
            New video
          </Link>
        )}
      </div>

      {/* Section label */}
      <div className="px-4 mb-1 flex-shrink-0">
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
          Conversations
        </p>
      </div>

      {/* Conversation list */}
      <div className="flex-1 overflow-y-auto px-2 pb-4 space-y-0.5">
        {isLoading && (
          <p className="text-xs text-gray-500 px-2 py-6 text-center">Loading&hellip;</p>
        )}

        {!isLoading && conversations?.length === 0 && (
          <p className="text-xs text-gray-500 px-2 py-6 text-center">
            No conversations yet.
          </p>
        )}

        {conversations?.map((conv) => (
          <ConversationItem
            key={conv.conversation_id}
            conv={conv}
            isActive={conv.conversation_id === currentConversationId}
            onDelete={() => void handleDelete(conv.conversation_id)}
            onRename={(title) =>
              rename.mutate({ conversationId: conv.conversation_id, title })
            }
          />
        ))}
      </div>

      {/* Footer hint */}
      <div className="px-4 py-3 flex-shrink-0 border-t border-gray-800">
        <p className="text-xs text-gray-600">Double-click a title to rename.</p>
      </div>
    </aside>
  );
}
