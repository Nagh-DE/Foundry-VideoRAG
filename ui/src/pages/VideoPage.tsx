import { useParams, useNavigate, Link } from 'react-router-dom';
import { useVideoSas } from '../hooks/useVideoSas';
import { useCreateConversation } from '../hooks/useConversations';
import VideoPlayer from '../components/VideoPlayer';

export default function VideoPage() {
  const { videoId } = useParams<{ videoId: string }>();
  const navigate = useNavigate();
  const { sasUrl, error: sasError } = useVideoSas(videoId);
  const createConv = useCreateConversation();

  async function handleNewConversation() {
    if (!videoId) return;
    try {
      const conv = await createConv.mutateAsync(videoId);
      navigate(`/chats/${conv.conversation_id}`);
    } catch {
      // Error displayed via createConv.error below
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-lg w-full max-w-3xl p-8 space-y-6">
        {/* Header row */}
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Link to="/" className="text-gray-400 hover:text-gray-600 transition-colors text-sm">
              &#8592; Home
            </Link>
            <span className="text-gray-300">|</span>
            <h2 className="text-xl font-bold text-gray-900">Video Ready</h2>
          </div>
          <button
            onClick={() => void handleNewConversation()}
            disabled={createConv.isPending}
            className="flex items-center gap-2 py-2 px-5 bg-indigo-600 text-white rounded-lg
                       text-sm font-semibold hover:bg-indigo-700 active:bg-indigo-800
                       disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {createConv.isPending ? (
              <>
                <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                Creating&hellip;
              </>
            ) : (
              'New conversation'
            )}
          </button>
        </div>

        {/* Errors */}
        {sasError && (
          <div className="p-3 bg-red-50 border border-red-200 rounded-lg">
            <p className="text-sm text-red-600">Could not load video: {sasError}</p>
          </div>
        )}

        {createConv.error && (
          <div className="p-3 bg-red-50 border border-red-200 rounded-lg">
            <p className="text-sm text-red-600">
              Could not create conversation: {(createConv.error as Error).message}
            </p>
          </div>
        )}

        {/* Video player */}
        {sasUrl ? (
          <VideoPlayer src={sasUrl} />
        ) : (
          !sasError && (
            <div className="h-64 bg-gray-100 rounded-xl flex flex-col items-center justify-center gap-2">
              <div className="w-6 h-6 border-2 border-indigo-400 border-t-transparent rounded-full animate-spin" />
              <p className="text-sm text-gray-400">Loading video&hellip;</p>
            </div>
          )
        )}

        <p className="text-xs text-gray-400 text-center">
          Click &quot;New conversation&quot; to start asking questions about this video.
        </p>
      </div>
    </div>
  );
}
