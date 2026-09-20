interface ProcessingBarProps {
  /** Human-readable stage label, e.g. "Extracting Frames" */
  stage: string;
  /** 0-100 */
  progress: number;
  /** Optional detail message from the backend */
  message?: string;
}

export default function ProcessingBar({ stage, progress, message }: ProcessingBarProps) {
  const clampedProgress = Math.max(0, Math.min(100, progress));

  return (
    <div className="space-y-2">
      <div className="flex justify-between items-baseline gap-2">
        <span className="text-sm font-semibold text-gray-800 truncate">{stage}</span>
        <span className="text-sm text-gray-500 flex-shrink-0 tabular-nums">
          {clampedProgress}%
        </span>
      </div>

      {/* Track */}
      <div className="h-2.5 bg-gray-200 rounded-full overflow-hidden">
        <div
          role="progressbar"
          aria-valuenow={clampedProgress}
          aria-valuemin={0}
          aria-valuemax={100}
          className="h-full bg-indigo-600 rounded-full transition-all duration-500 ease-out"
          style={{ width: `${clampedProgress}%` }}
        />
      </div>

      {/* Optional detail message */}
      {message && (
        <p className="text-xs text-gray-500 leading-relaxed">{message}</p>
      )}
    </div>
  );
}
