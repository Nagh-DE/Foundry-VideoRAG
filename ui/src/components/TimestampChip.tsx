import type { Citation } from '../types';

function formatSeconds(totalSeconds: number): string {
  const h = Math.floor(totalSeconds / 3600);
  const m = Math.floor((totalSeconds % 3600) / 60);
  const s = Math.floor(totalSeconds % 60);

  if (h > 0) {
    return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  }
  return `${m}:${String(s).padStart(2, '0')}`;
}

function buildLabel(citation: Citation): string {
  const start = formatSeconds(citation.start_seconds);
  if (citation.end_seconds > citation.start_seconds) {
    const end = formatSeconds(citation.end_seconds);
    return `${start}–${end}`;
  }
  return start;
}

interface TimestampChipProps {
  citation: Citation;
  onSeek: (citation: Citation) => void;
}

export default function TimestampChip({ citation, onSeek }: TimestampChipProps) {
  const label = buildLabel(citation);

  return (
    <button
      type="button"
      onClick={() => onSeek(citation)}
      className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-mono
                 bg-indigo-50 text-indigo-700 border border-indigo-200
                 hover:bg-indigo-100 hover:border-indigo-300 active:bg-indigo-200
                 transition-colors cursor-pointer"
      title={`Jump to ${label} in the video`}
    >
      [{label}]
    </button>
  );
}
