import { useEffect, useState } from "react";
import { getStatus, getDownloadUrl } from "../lib/utils/api";
import type { StatusResponse } from "../types";
import { Download, AlertCircle, Loader2 } from "lucide-react";

interface ProcessingStatusProps {
  jobId: string;
  onRetry: () => void;
}

export function ProcessingStatus({ jobId, onRetry }: ProcessingStatusProps) {
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
    }, 2000);

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
    return (
      <div className="flex flex-col items-center gap-4">
        <div className="w-16 h-16 bg-green-500/10 rounded-full flex items-center justify-center">
          <Download className="w-8 h-8 text-green-500" />
        </div>
        <p className="text-lg font-medium">Ready!</p>
        <a
          href={getDownloadUrl(jobId)}
          download="swapped.mp4"
          className="py-3 px-8 bg-primary text-primary-foreground rounded-xl font-medium hover:bg-primary/90 transition-colors inline-flex items-center gap-2"
        >
          <Download className="w-4 h-4" />
          Download Video
        </a>
      </div>
    );
  }

  const pct = Math.round(status.progress * 100);
  return (
    <div className="flex flex-col items-center gap-6 w-full max-w-md">
      <Loader2 className="w-10 h-10 animate-spin text-primary" />
      <p className="text-lg font-medium">Swapping faces...</p>
      <div className="w-full bg-muted rounded-full h-3 overflow-hidden">
        <div
          className="h-full bg-primary rounded-full transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="text-sm text-muted-foreground">{pct}% complete</p>
    </div>
  );
}
