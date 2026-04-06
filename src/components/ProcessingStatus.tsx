import { useEffect, useState } from "react";
import { getStatus, getDownloadUrl } from "@veed-hackathon/lib/utils/api";
import type { StatusResponse } from "@veed-hackathon/types";
import { Download, RotateCcw, User } from "lucide-react";
import { MediaPreview } from "@veed-hackathon/components/MediaPreview";
import { Alert, AlertTitle, AlertDescription } from "@veed-hackathon/components/ui/alert";
import { Button } from "@veed-hackathon/components/ui/button";
import { Progress, ProgressIndicator, ProgressTrack } from "@veed-hackathon/components/ui/progress";
import { Spinner } from "@veed-hackathon/components/ui/spinner";

interface ProcessingStatusProps {
  jobId: string;
  onRetry: () => void;
  onStartOver: () => void;
  onEditResult: (jobId: string) => void;
  onError: (error: string) => void;
}

export function ProcessingStatus({
  jobId,
  onRetry,
  onStartOver,
  onEditResult,
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
      <div className="flex flex-col items-center gap-6 text-center max-w-md w-full animate-in fade-in slide-in-from-bottom-4 duration-500">
        <Alert variant="error">
          <AlertTitle>Processing failed</AlertTitle>
          <AlertDescription>{status.error}</AlertDescription>
        </Alert>
        <Button onClick={onRetry} size="xl">
          Try Again
        </Button>
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
      <div className="flex flex-col items-center gap-8 w-full max-w-lg animate-in fade-in slide-in-from-bottom-4 duration-500">
        <MediaPreview
          src={downloadUrl}
          mediaType={status.media_type}
          alt={`Generated ${mediaLabel.toLowerCase()} preview`}
        />
        
        {status.warnings && status.warnings.length > 0 && (
          <Alert variant="warning">
            <AlertTitle>Reference generation warning</AlertTitle>
            <AlertDescription>
              {status.warnings.map((warning, i) => (
                <p key={i}>{warning}</p>
              ))}
            </AlertDescription>
          </Alert>
        )}
        
        <div className="flex flex-wrap items-center justify-center gap-3">
          <Button 
            size="lg" 
            className="min-w-40"
            render={
              <a href={downloadUrl} download={downloadFilename}>
                <Download className="mr-2 h-4 w-4" />
                Download {mediaLabel}
              </a>
            }
          />
          
          <Button variant="outline" size="lg" onClick={onStartOver}>
            <RotateCcw className="mr-2 h-4 w-4" />
            Start Over
          </Button>
          
          <Button variant="secondary" size="lg" onClick={() => onEditResult(jobId)}>
            <User className="mr-2 h-4 w-4" />
            Edit Faces
          </Button>
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
    <div className="flex flex-col items-center gap-8 w-full max-w-md animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="flex flex-col items-center gap-4 text-center">
        <Spinner className="h-10 w-10 text-primary" />
        <div className="space-y-1.5 mt-2">
          <h3 className="text-xl font-black tracking-tight text-slate-950">{phaseLabel}</h3>
          <p className="text-sm font-medium text-slate-500 max-w-xs mx-auto">
            {status.message ?? "Working through the selected media"}
          </p>
        </div>
      </div>

      {status.warnings && status.warnings.length > 0 && (
        <Alert variant="warning">
          <AlertTitle>Reference generation warning</AlertTitle>
          <AlertDescription>
            {status.warnings.map((warning, i) => (
              <p key={i}>{warning}</p>
            ))}
          </AlertDescription>
        </Alert>
      )}

      <div className="w-full space-y-3">
        <div className="flex items-center justify-between gap-4">
          <span className="text-sm font-bold text-slate-900">{pct}% complete</span>
          {hasFrameProgress && (
            <span className="text-xs font-semibold tabular-nums text-slate-500">
              {status.completed_frames}/{status.total_frames} frames
            </span>
          )}
        </div>
        
        <Progress value={pct}>
          <ProgressTrack>
            <ProgressIndicator />
          </ProgressTrack>
        </Progress>
      </div>
    </div>
  );
}
