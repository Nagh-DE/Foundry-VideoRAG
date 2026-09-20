import { useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useProcessingStatus } from '../hooks/useProcessingStatus';
import ProcessingBar from '../components/ProcessingBar';

function formatStage(stage: string): string {
  return stage
    .replace(/_/g, ' ')
    .replace(/-/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function ProcessingPage() {
  const { videoId } = useParams<{ videoId: string }>();
  const navigate = useNavigate();
  const { data: status, error } = useProcessingStatus(videoId);

  useEffect(() => {
    if (status?.status === 'ready') {
      navigate(`/videos/${videoId}`, { replace: true });
    }
  }, [status?.status, videoId, navigate]);

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-lg w-full max-w-md p-8">
        {/* Header */}
        <div className="mb-6">
          <div className="flex items-center gap-3 mb-2">
            {status?.status !== 'failed' && (
              <div className="w-5 h-5 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin flex-shrink-0" />
            )}
            <h2 className="text-xl font-bold text-gray-900">
              {status?.status === 'failed' ? 'Processing Failed' : 'Processing Video'}
            </h2>
          </div>
          {status?.status !== 'failed' && (
            <p className="text-sm text-gray-500">
              This may take a few minutes. Please keep this page open.
            </p>
          )}
        </div>

        {/* Network error */}
        {error && (
          <div className="p-3 bg-red-50 border border-red-200 rounded-lg mb-4">
            <p className="text-sm text-red-600">Connection error: {(error as Error).message}</p>
          </div>
        )}

        {/* Failed state */}
        {status?.status === 'failed' ? (
          <div className="space-y-4">
            <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
              <p className="text-sm font-semibold text-red-700">Processing could not be completed.</p>
              {status.message && (
                <p className="text-sm text-red-600 mt-1">{status.message}</p>
              )}
              {status.stage && (
                <p className="text-xs text-red-500 mt-1">
                  Failed at stage: {formatStage(status.stage)}
                </p>
              )}
            </div>
            <Link
              to="/"
              className="block w-full text-center py-2.5 px-4 bg-indigo-600 text-white
                         rounded-lg text-sm font-semibold hover:bg-indigo-700 transition-colors"
            >
              Try again
            </Link>
          </div>
        ) : (
          /* Processing / initializing state */
          <div className="space-y-3">
            <ProcessingBar
              stage={status ? formatStage(status.stage || 'initializing') : 'Initializing…'}
              progress={status?.progress ?? 0}
              message={status?.message}
            />
            {!status && !error && (
              <p className="text-xs text-gray-400 text-center">Connecting to server&hellip;</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
