import { useEffect, useState } from "react";
import { getStatus, getDownloadUrl } from "../lib/utils/api";
import type { StatusResponse } from "../types";
import { Download, AlertCircle, Loader2, RotateCcw } from "lucide-react";
import { VideoPreview } from "./VideoPreview";

interface ProcessingStatusProps {
  jobId: string;
  onRetry: () => void;
  onStartOver: () => void;
}

export function ProcessingStatus({
  jobId,
  onRetry,
  onStartOver,
}: ProcessingStatusProps) {
  const [status, setStatus] = useState<StatusResponse>({
    status: "processing",
    progress: 0,
    error: null,
  });

  useEffect(() => {
    if (status.status !== "processing") return;

    const interval = setInterval(async () => {
      try {
        const s = await getStatus(jobId);
        setStatus(s);
        if (s.status !== "processing") clearInterval(interval);
      } catch {
        // Keep polling on transient errors
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [jobId, status.status]);

  if (status.status === "failed") {
    return (
      <div className="flex flex-col items-center gap-4 text-center">
        <AlertCircle className="w-12 h-12 text-destructive" />
        <p className="text-lg font-medium">Processing failed</p>
        <p className="text-sm text-muted-foreground">{status.error}</p>
        <button
          className="py-2 px-6 bg-primary text-primary-foreground rounded-xl font-medium hover:bg-primary/90 transition-colors"
          onClick={onRetry}
        >
          Try Again
        </button>
      </div>
    );
  }

  if (status.status === "completed") {
    const downloadUrl = getDownloadUrl(jobId);
    return (
      <div className="flex flex-col items-center gap-6 w-full max-w-lg">
        <VideoPreview src={downloadUrl} />
        <div className="flex gap-3">
          <a
            href={downloadUrl}
            download="swapped.mp4"
            className="py-3 px-8 bg-primary text-primary-foreground rounded-xl font-medium hover:bg-primary/90 transition-colors inline-flex items-center gap-2"
          >
            <Download className="w-4 h-4" />
            Download Video
          </a>
          <button
            className="py-3 px-6 border border-muted-foreground/25 text-foreground rounded-xl font-medium hover:bg-muted transition-colors inline-flex items-center gap-2"
            onClick={onStartOver}
          >
            <RotateCcw className="w-4 h-4" />
            Start Over
          </button>
        </div>
      </div>
    );
  }

  const pct = Math.round(status.progress * 100);
  const phaseLabel =
    status.phase === "extracting_clips"
      ? "Preparing clip"
      : status.phase === "swapping"
        ? "Swapping frames"
        : status.phase === "compositing"
          ? "Compositing frames"
          : status.phase === "rendering"
            ? "Rendering video"
            : status.phase === "lipsync"
              ? "Applying lipsync"
              : "Processing";
  const hasFrameProgress =
    typeof status.completed_frames === "number" &&
    typeof status.total_frames === "number" &&
    status.total_frames > 0;
  return (
    <div className="flex flex-col items-center gap-6 w-full max-w-md">
      <Loader2 className="w-10 h-10 animate-spin text-primary" />
      <div className="space-y-1 text-center">
        <p className="text-lg font-medium">{phaseLabel}</p>
        <p className="text-sm text-muted-foreground">
          {status.message ?? "Working through the selected clip"}
        </p>
      </div>
      <div className="w-full bg-muted rounded-full h-3 overflow-hidden">
        <div
          className="h-full bg-primary rounded-full transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="space-y-1 text-center">
        <p className="text-sm text-muted-foreground">{pct}% complete</p>
        {hasFrameProgress && (
          <p className="text-xs text-muted-foreground">
            {status.completed_frames}/{status.total_frames} frames
          </p>
        )}
      </div>
    </div>
  );
}
