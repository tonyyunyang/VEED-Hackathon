import { useState } from "react";
import "./App.css";
import "./index.css";
import type { AppStep, FaceInfo } from "./types";
import { uploadVideo, startSwap } from "./lib/utils/api";
import { VideoUploader } from "./components/VideoUploader";
import { FaceSelector } from "./components/FaceSelector";
import { ProcessingStatus } from "./components/ProcessingStatus";
import { Gallery } from "./components/Gallery";
import { VideoPlayer } from "./components/VideoPlayer";
import { Loader2, ArrowLeft } from "lucide-react";

function App() {
  const [step, setStep] = useState<AppStep>("gallery");
  const [videoId, setVideoId] = useState("");
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [selectedVideoSrc, setSelectedVideoSrc] = useState<string>("");
  const [faces, setFaces] = useState<FaceInfo[]>([]);
  const [jobId, setJobId] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const [isSwapping, setIsSwapping] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleUpload = async (file: File) => {
    setIsUploading(true);
    setError(null);
    setVideoFile(file);
    try {
      const vid = await uploadVideo(file);
      setVideoId(vid);
      // For the hackathon, we navigate to the player after upload
      const url = URL.createObjectURL(file);
      setSelectedVideoSrc(url);
      setStep("player");
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

  const handleStartOver = () => {
    setStep("gallery");
    setVideoId("");
    setVideoFile(null);
    setSelectedVideoSrc("");
    setFaces([]);
    setJobId("");
    setError(null);
  };

  return (
    <div className="w-full min-h-screen bg-background font-sans flex flex-col items-center p-8">
      {step !== "player" && (
        <h1 className="text-4xl font-black mb-12 tracking-tight bg-gradient-to-r from-primary to-purple-600 bg-clip-text text-transparent">
          VEED Face Swapper
        </h1>
      )}

      {error && (
        <div className="mb-6 p-4 bg-destructive/10 text-destructive rounded-xl text-sm max-w-lg w-full text-center">
          {error}
        </div>
      )}

      {step === "gallery" && (
        <Gallery
          onSelect={(src) => {
            setSelectedVideoSrc(src);
            setStep("player");
          }}
          onUploadClick={() => setStep("upload")}
        />
      )}

      {step === "upload" && (
        <div className="flex flex-col items-center gap-6 w-full max-w-2xl">
          <div className="flex items-center justify-between w-full mb-4">
            <button
              onClick={() => setStep("gallery")}
              className="flex items-center gap-2 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
              Back to Gallery
            </button>
          </div>
          <VideoUploader onUpload={handleUpload} isUploading={isUploading} />
        </div>
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
          videoFile={videoFile}
          onSwap={handleSwap}
          isSwapping={isSwapping}
        />
      )}

      {step === "processing" && (
        <ProcessingStatus
          jobId={jobId}
          onRetry={() => setStep("select")}
          onStartOver={handleStartOver}
        />
      )}

      {step === "player" && (
        <div className="w-full h-screen fixed inset-0 z-50">
          <VideoPlayer
            videoSrc={selectedVideoSrc}
            onBack={() => setStep("gallery")}
          />
        </div>
      )}
    </div>
  );
}

export default App;
