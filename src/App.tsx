import { useState } from "react";
import "./App.css";
import "./index.css";
import type { AppStep, FaceInfo } from "./types";
import { uploadVideo, detectFaces, startSwap } from "./lib/utils/api";
import { VideoUploader } from "./components/VideoUploader";
import { FaceSelector } from "./components/FaceSelector";
import { ProcessingStatus } from "./components/ProcessingStatus";
import { Loader2 } from "lucide-react";

function App() {
  const [step, setStep] = useState<AppStep>("upload");
  const [videoId, setVideoId] = useState("");
  const [faces, setFaces] = useState<FaceInfo[]>([]);
  const [jobId, setJobId] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const [isSwapping, setIsSwapping] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleUpload = async (file: File) => {
    setIsUploading(true);
    setError(null);
    try {
      const vid = await uploadVideo(file);
      setVideoId(vid);
      setStep("detecting");

      const result = await detectFaces(vid);
      setFaces(result.faces);
      setStep("select");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
      setStep("upload");
    } finally {
      setIsUploading(false);
    }
  };

  const handleSwap = async (selectedIds: string[]) => {
    setIsSwapping(true);
    setError(null);
    try {
      const jid = await startSwap(videoId, selectedIds);
      setJobId(jid);
      setStep("processing");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Swap failed");
    } finally {
      setIsSwapping(false);
    }
  };

  return (
    <div className="w-full min-h-screen bg-background font-sans flex flex-col items-center justify-center p-8">
      <h1 className="text-3xl font-bold mb-8">Face Swap</h1>

      {error && (
        <div className="mb-6 p-4 bg-destructive/10 text-destructive rounded-xl text-sm max-w-lg w-full text-center">
          {error}
        </div>
      )}

      {step === "upload" && (
        <VideoUploader onUpload={handleUpload} isUploading={isUploading} />
      )}

      {step === "detecting" && (
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="w-10 h-10 animate-spin text-primary" />
          <p className="text-lg font-medium">Analyzing faces...</p>
          <p className="text-sm text-muted-foreground">
            This may take up to a minute
          </p>
        </div>
      )}

      {step === "select" && (
        <FaceSelector
          faces={faces}
          onSwap={handleSwap}
          isSwapping={isSwapping}
        />
      )}

      {step === "processing" && (
        <ProcessingStatus jobId={jobId} onRetry={() => setStep("select")} />
      )}
    </div>
  );
}

export default App;
