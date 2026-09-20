import { useRef, useState, useCallback } from 'react';

interface UploadDropzoneProps {
  onFile: (file: File) => void;
}

export default function UploadDropzone({ onFile }: UploadDropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [dragError, setDragError] = useState<string | null>(null);

  const processFile = useCallback(
    (file: File) => {
      if (file.type !== 'video/mp4' && !file.name.toLowerCase().endsWith('.mp4')) {
        setDragError('Only MP4 files are accepted.');
        return;
      }
      setDragError(null);
      onFile(file);
    },
    [onFile]
  );

  function handleDragOver(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragging(true);
  }

  function handleDragLeave(e: React.DragEvent<HTMLDivElement>) {
    // Only clear drag state if leaving the zone entirely
    if (!e.currentTarget.contains(e.relatedTarget as Node)) {
      setDragging(false);
    }
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) processFile(file);
  }

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) processFile(file);
    // Reset so the same file can be re-selected
    e.target.value = '';
  }

  return (
    <div>
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') inputRef.current?.click(); }}
        aria-label="Upload MP4 file. Click or drag and drop."
        className={`border-2 border-dashed rounded-xl p-10 text-center cursor-pointer
                    transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-400 ${
                      dragging
                        ? 'border-indigo-500 bg-indigo-50'
                        : 'border-gray-300 hover:border-indigo-400 hover:bg-gray-50'
                    }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".mp4,video/mp4"
          className="hidden"
          onChange={handleChange}
        />

        {/* Upload icon */}
        <div
          className={`w-12 h-12 mx-auto mb-3 rounded-full flex items-center justify-center text-2xl
                      transition-colors ${dragging ? 'bg-indigo-100 text-indigo-600' : 'bg-gray-100 text-gray-400'}`}
        >
          &#8679;
        </div>

        <p className="text-sm font-semibold text-gray-700">
          {dragging ? 'Drop your MP4 here' : 'Drag & drop your MP4 here'}
        </p>
        <p className="text-xs text-gray-400 mt-1">or click to browse files</p>
        <p className="text-xs text-gray-300 mt-2">MP4 files only</p>
      </div>

      {dragError && (
        <p className="text-xs text-red-500 mt-1.5">{dragError}</p>
      )}
    </div>
  );
}
