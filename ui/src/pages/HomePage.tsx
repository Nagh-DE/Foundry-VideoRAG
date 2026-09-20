import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { uploadVideo, uploadVideoFromUrl, submitVideoLink, processVideo } from '../services/api';
import UploadDropzone from '../components/UploadDropzone';

type Tab = 'upload' | 'url' | 'youtube';

const TABS: { key: Tab; label: string }[] = [
  { key: 'upload', label: 'Upload MP4' },
  { key: 'url', label: 'Direct URL' },
  { key: 'youtube', label: 'Video Link' },
];

export default function HomePage() {
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>('upload');
  const [file, setFile] = useState<File | null>(null);
  const [url, setUrl] = useState('');
  const [youtubeUrl, setYoutubeUrl] = useState('');
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const handleFileDrop = useCallback((f: File) => {
    setFile(f);
    setError(null);
  }, []);

  function switchTab(t: Tab) {
    setTab(t);
    setError(null);
    setUploadProgress(0);
  }

  async function handleUpload() {
    if (!file) return;
    setUploading(true);
    setError(null);
    setUploadProgress(0);
    try {
      const uploaded = await uploadVideo(file, (pct) => setUploadProgress(pct));
      await processVideo(uploaded.video_id);
      navigate(`/videos/${uploaded.video_id}/processing`);
    } catch (e) {
      setError((e as Error).message);
      setUploading(false);
    }
  }

  async function handleUrlProcess() {
    if (!url.trim()) return;
    setUploading(true);
    setError(null);
    try {
      const uploaded = await uploadVideoFromUrl(url.trim());
      await processVideo(uploaded.video_id);
      navigate(`/videos/${uploaded.video_id}/processing`);
    } catch (e) {
      setError((e as Error).message);
      setUploading(false);
    }
  }

  async function handleYoutubeProcess() {
    if (!youtubeUrl.trim()) return;
    setUploading(true);
    setError(null);
    try {
      // Backend downloads + processes in the background; returns video_id immediately.
      const result = await submitVideoLink(youtubeUrl.trim());
      navigate(`/videos/${result.video_id}/processing`);
    } catch (e) {
      setError((e as Error).message);
      setUploading(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-lg w-full max-w-xl p-8">
        {/* Header */}
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-gray-900">Video RAG</h1>
          <p className="text-gray-500 mt-1 text-sm">
            Upload or link a video to start a retrieval-augmented conversation.
          </p>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-gray-200 mb-6">
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => switchTab(t.key)}
              className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
                tab === t.key
                  ? 'border-indigo-600 text-indigo-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Upload tab */}
        {tab === 'upload' && (
          <div className="space-y-4">
            <UploadDropzone onFile={handleFileDrop} />

            {file && (
              <div className="flex items-center gap-2 text-sm text-gray-600 bg-gray-50 rounded-lg px-3 py-2">
                <span className="text-gray-400">&#128196;</span>
                <span className="font-medium truncate">{file.name}</span>
                <span className="text-gray-400 flex-shrink-0">
                  ({(file.size / 1024 / 1024).toFixed(1)} MB)
                </span>
                {!uploading && (
                  <button
                    onClick={() => setFile(null)}
                    className="ml-auto text-gray-400 hover:text-gray-600 flex-shrink-0"
                  >
                    &#215;
                  </button>
                )}
              </div>
            )}

            {uploading && (
              <div>
                <div className="flex justify-between text-xs text-gray-500 mb-1">
                  <span>Uploading&hellip;</span>
                  <span>{uploadProgress}%</span>
                </div>
                <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-indigo-600 rounded-full transition-all duration-200"
                    style={{ width: `${uploadProgress}%` }}
                  />
                </div>
              </div>
            )}

            <button
              onClick={() => void handleUpload()}
              disabled={!file || uploading}
              className="w-full py-2.5 px-4 bg-indigo-600 text-white rounded-lg text-sm font-semibold
                         hover:bg-indigo-700 active:bg-indigo-800
                         disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {uploading ? 'Uploading…' : 'Upload & Process'}
            </button>
          </div>
        )}

        {/* Direct URL tab */}
        {tab === 'url' && (
          <div className="space-y-4">
            <div>
              <label htmlFor="video-url" className="block text-sm font-medium text-gray-700 mb-1.5">
                Direct MP4 URL (public HTTPS only)
              </label>
              <input
                id="video-url"
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') void handleUrlProcess(); }}
                placeholder="https://example.com/video.mp4"
                disabled={uploading}
                className="w-full border border-gray-300 rounded-lg px-3.5 py-2.5 text-sm
                           focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent
                           disabled:bg-gray-50 disabled:text-gray-400"
              />
            </div>

            <button
              onClick={() => void handleUrlProcess()}
              disabled={!url.trim() || uploading}
              className="w-full py-2.5 px-4 bg-indigo-600 text-white rounded-lg text-sm font-semibold
                         hover:bg-indigo-700 active:bg-indigo-800
                         disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {uploading ? 'Processing…' : 'Process URL'}
            </button>
          </div>
        )}

        {/* YouTube tab */}
        {tab === 'youtube' && (
          <div className="space-y-4">
            <div>
              <label htmlFor="yt-url" className="block text-sm font-medium text-gray-700 mb-1.5">
                Video URL (YouTube, Vimeo, and more)
              </label>
              <input
                id="yt-url"
                type="url"
                value={youtubeUrl}
                onChange={(e) => setYoutubeUrl(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') void handleYoutubeProcess(); }}
                placeholder="https://www.youtube.com/watch?v=... or https://vimeo.com/..."
                disabled={uploading}
                className="w-full border border-gray-300 rounded-lg px-3.5 py-2.5 text-sm
                           focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent
                           disabled:bg-gray-50 disabled:text-gray-400"
              />
              <p className="text-xs text-gray-400 mt-1.5">
                Video is downloaded and indexed in the background — you'll see progress immediately.
              </p>
            </div>

            <button
              onClick={() => void handleYoutubeProcess()}
              disabled={!youtubeUrl.trim() || uploading}
              className="w-full py-2.5 px-4 bg-indigo-600 text-white rounded-lg text-sm font-semibold
                         hover:bg-indigo-700 active:bg-indigo-800
                         disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {uploading ? 'Submitting…' : 'Download & Process'}
            </button>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg">
            <p className="text-sm text-red-600">{error}</p>
          </div>
        )}
      </div>
    </div>
  );
}
