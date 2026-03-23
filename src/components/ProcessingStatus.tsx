import { useEffect, useState } from "react";
import { getStatus, getDownloadUrl } from "../lib/utils/api";
import type { StatusResponse } from "../types";
import { Download, AlertCircle, Loader2, RotateCcw } from "lucide-react";
import { MediaPreview } from "./MediaPreview";

interface ProcessingStatusProps {
  jobId: string;
  onRetry: () => void;
  onStartOver: () => void;
  onError: (error: string) => void;
}

export function ProcessingStatus({
  jobId,
  onRetry,
  onStartOver,
  onError,
}: ProcessingStatusProps) {
  const [status, setStatus] = useState<StatusResponse>({
    status: "processing",
    progress: 0,
    error: null,
    warnings: null,
  });

  useEffect(() => {
    if (status.status === "failed" && status.error) {
      onError(status.error);
    }
  }, [status.status, status.error, onError]);

  useEffect(() => {
    setStatus({
      status: "processing",
      progress: 0,
      error: null,
      warnings: null,
    });
  }, [jobId]);

  useEffect(() => {
    if (status.status !== "processing") return;

    let active = true;

    const poll = async () => {
      try {
        const s = await getStatus(jobId);
        if (!active) return;
        setStatus(s);
      } catch {
        // Keep polling on transient errors
      }
    };

    void poll();
    const interval = setInterval(() => {
      void poll();
    }, 1000);

    return () => {
      active = false;
      clearInterval(interval);
    };
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
    const downloadFilename =
      status.output_filename ??
      (status.media_type === "image" ? "swapped.png" : "swapped.mp4");
    const mediaLabel = status.media_type === "image" ? "Image" : "Video";
    return (
      <div className="flex flex-col items-center gap-6 w-full max-w-lg">
        <MediaPreview
          src={downloadUrl}
          mediaType={status.media_type}
          alt={`Generated ${mediaLabel.toLowerCase()} preview`}
        />
        {status.warnings && status.warnings.length > 0 && (
          <div className="w-full rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-left text-sm text-amber-900">
            <div className="mb-1 flex items-center gap-2 font-medium">
              <AlertCircle className="h-4 w-4 text-amber-700" />
              Reference generation warning
            </div>
            {status.warnings.map((warning) => (
              <p key={warning}>{warning}</p>
            ))}
          </div>
        )}
        <div className="flex gap-3">
          <a
            href={downloadUrl}
            download={downloadFilename}
            className="py-3 px-8 bg-primary text-primary-foreground rounded-xl font-medium hover:bg-primary/90 transition-colors inline-flex items-center gap-2"
          >
            <Download className="w-4 h-4" />
            Download {mediaLabel}
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
      ? "Preparing selection"
      : status.phase === "swapping"
        ? "Swapping faces"
      : status.phase === "compositing"
          ? "Compositing result"
        : status.phase === "rendering"
            ? status.media_type === "image"
              ? "Rendering image"
              : "Rendering video"
            : status.phase === "lipsync"
              ? "Applying lipsync"
              : "Processing media";
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
          {status.message ?? "Working through the selected media"}
        </p>
      </div>
      {status.warnings && status.warnings.length > 0 && (
        <div className="w-full rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-left text-sm text-amber-900">
          <div className="mb-1 flex items-center gap-2 font-medium">
            <AlertCircle className="h-4 w-4 text-amber-700" />
            Reference generation warning
          </div>
          {status.warnings.map((warning) => (
            <p key={warning}>{warning}</p>
          ))}
        </div>
      )}
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
