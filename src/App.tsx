import { useEffect, useRef, useState } from "react";
import "./App.css";
import "./index.css";
import type { AppStep, FaceInfo } from "./types";
import { detectFaces, uploadVideo, startSwap } from "./lib/utils/api";
import { VideoUploader } from "./components/VideoUploader";
import { ProcessingStatus } from "./components/ProcessingStatus";
import { Gallery } from "./components/Gallery";
import { VideoPlayer } from "./components/VideoPlayer";
import { PartnerStrip } from "./components/PartnerStrip";
import { Loader2, ArrowLeft } from "lucide-react";

function App() {
  const [step, setStep] = useState<AppStep>("gallery");
  const [videoId, setVideoId] = useState("");
  const [selectedVideoSrc, setSelectedVideoSrc] = useState<string>("");
  const [faces, setFaces] = useState<FaceInfo[]>([]);
  const [detectionFps, setDetectionFps] = useState(0);
  const [jobId, setJobId] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const [isSwapping, setIsSwapping] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const uploadedPreviewUrlRef = useRef<string | null>(null);
  const uploadInFlightRef = useRef(false);

  const clearUploadedPreview = () => {
    if (uploadedPreviewUrlRef.current) {
      URL.revokeObjectURL(uploadedPreviewUrlRef.current);
      uploadedPreviewUrlRef.current = null;
    }
  };

  useEffect(() => clearUploadedPreview, []);

  const handleUpload = async (file: File) => {
    if (uploadInFlightRef.current) return;
    uploadInFlightRef.current = true;
    setIsUploading(true);
    setError(null);
    setFaces([]);
    setDetectionFps(0);
    setJobId("");
    clearUploadedPreview();
    const url = URL.createObjectURL(file);
    uploadedPreviewUrlRef.current = url;
    setSelectedVideoSrc(url);
    setStep("detecting");
    try {
      const vid = await uploadVideo(file);
      setVideoId(vid);
      const detection = await detectFaces(vid);
      setDetectionFps(detection.fps);
      setFaces(detection.faces);
      setStep("player");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
      setStep("upload");
    } finally {
      uploadInFlightRef.current = false;
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
    clearUploadedPreview();
    setStep("gallery");
    setVideoId("");
    setSelectedVideoSrc("");
    setFaces([]);
    setDetectionFps(0);
    setJobId("");
    setError(null);
  };

  const handleOpenGalleryVideo = (src: string) => {
    clearUploadedPreview();
    setError(null);
    setVideoId("");
    setFaces([]);
    setDetectionFps(0);
    setJobId("");
    setSelectedVideoSrc(src);
    setStep("player");
  };

  return (
    <div className="relative flex min-h-screen w-full flex-col items-center overflow-hidden bg-[radial-gradient(circle_at_top,_rgba(167,255,124,0.18),transparent_24%),radial-gradient(circle_at_20%_80%,_rgba(255,111,97,0.12),transparent_28%),radial-gradient(circle_at_80%_20%,_rgba(122,87,255,0.14),transparent_28%),linear-gradient(180deg,_#f7fbf1_0%,_#eef3ff_100%)] p-8 font-sans">
      <div className="pointer-events-none absolute -left-16 top-12 h-64 w-64 rounded-full bg-lime-300/20 blur-3xl" />
      <div className="pointer-events-none absolute right-0 top-24 h-72 w-72 rounded-full bg-violet-400/14 blur-3xl" />
      <div className="pointer-events-none absolute bottom-0 left-1/3 h-72 w-72 rounded-full bg-orange-300/12 blur-3xl" />
      <div className="relative z-10 flex w-full flex-col items-center">
      {step !== "player" && (
        <div className="mb-12 flex flex-col items-center gap-4 rounded-[36px] border border-black/6 bg-white/62 px-8 py-6 shadow-[0_30px_90px_rgba(15,23,42,0.08)] backdrop-blur-2xl">
          <div className="rounded-full border border-black/8 bg-black/4 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-500">
            VEED Hackathon Build
          </div>
          <h1 className="bg-[linear-gradient(135deg,#121826_0%,#2b3246_28%,#7a57ff_56%,#75df84_100%)] bg-clip-text text-4xl font-black tracking-tight text-transparent md:text-5xl">
            VEED Face Swapper
          </h1>
          <p className="max-w-2xl text-center text-sm leading-6 text-slate-500">
            Live face detection, clip-aware selection, and a single editor flow for reviewing tracks before swap.
          </p>
          <PartnerStrip compact />
        </div>
      )}

      {error && (
        <div className="mb-6 p-4 bg-destructive/10 text-destructive rounded-xl text-sm max-w-lg w-full text-center">
          {error}
        </div>
      )}

      {step === "gallery" && (
        <Gallery
          onSelect={handleOpenGalleryVideo}
          onUploadClick={() => {
            setError(null);
            setStep("upload");
          }}
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
            Uploading the clip and running face detection
          </p>
        </div>
      )}

      {step === "processing" && (
        <ProcessingStatus
          jobId={jobId}
          onRetry={() => setStep("player")}
          onStartOver={handleStartOver}
        />
      )}

      {step === "player" && (
        <div className="w-full h-screen fixed inset-0 z-50">
          <VideoPlayer
            videoSrc={selectedVideoSrc}
            faces={faces}
            fps={detectionFps}
            useLiveTracking={Boolean(videoId)}
            error={error}
            isSwapping={isSwapping}
            onSwap={videoId ? handleSwap : undefined}
            onBack={handleStartOver}
          />
        </div>
      )}
      </div>
    </div>
  );
}

export default App;
