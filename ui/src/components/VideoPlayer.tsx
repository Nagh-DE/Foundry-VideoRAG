import { forwardRef, useImperativeHandle, useRef } from 'react';

export interface VideoPlayerHandle {
  seekTo: (seconds: number) => void;
}

interface VideoPlayerProps {
  src: string;
  /** When true, constrains height to ~220px for the compact chat header player. */
  compact?: boolean;
}

const VideoPlayer = forwardRef<VideoPlayerHandle, VideoPlayerProps>(
  ({ src, compact = false }, ref) => {
    const videoEl = useRef<HTMLVideoElement>(null);

    useImperativeHandle(ref, () => ({
      seekTo(seconds: number) {
        const el = videoEl.current;
        if (!el) return;
        el.currentTime = seconds;
        el.play().catch(() => {
          // Autoplay may be blocked by the browser; user can press play manually
        });
      },
    }));

    return (
      <video
        ref={videoEl}
        src={src}
        controls
        className={`w-full rounded-lg bg-black object-contain ${
          compact ? 'max-h-[220px]' : 'max-h-[480px]'
        }`}
      />
    );
  }
);

VideoPlayer.displayName = 'VideoPlayer';

export default VideoPlayer;
