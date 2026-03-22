import { useEffect, useRef, useState } from "react";
import { Routes, Route, useNavigate, useLocation } from "react-router-dom";
import "./App.css";
import "./index.css";
import type { AppStep, FaceInfo } from "./types";
import {
  detectFaces,
  uploadVideo,
  startSwap,
  uploadReference,
} from "./lib/utils/api";
import { VideoUploader } from "./components/VideoUploader";
import { ProcessingStatus } from "./components/ProcessingStatus";
import { Gallery } from "./components/Gallery";
import { VideoPlayer } from "./components/VideoPlayer";
import { ImageEditor } from "./components/ImageEditor";
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
  const [userVideos, setUserVideos] = useState<
    { name: string; url: string; file: File }[]
  >([]);
  const uploadedPreviewUrlRef = useRef<string | null>(null);
  const uploadInFlightRef = useRef(false);
  const navigate = useNavigate();
  const location = useLocation();

  const clearUploadedPreview = () => {
    if (uploadedPreviewUrlRef.current) {
      URL.revokeObjectURL(uploadedPreviewUrlRef.current);
      uploadedPreviewUrlRef.current = null;
    }
  };

  useEffect(() => clearUploadedPreview, []);

  // Sync route and step state
  useEffect(() => {
    if (location.pathname === "/" && step !== "gallery" && step !== "upload") {
      setStep("gallery");
    } else if (
      location.pathname.startsWith("/editor") &&
      !selectedVideoSrc &&
      step !== "detecting"
    ) {
      navigate("/", { replace: true });
    }
  }, [location.pathname, step, selectedVideoSrc, navigate]);

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
    navigate("/editor");
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

  const handleSwap = async (
    selectedIds: string[],
    frameWindow?: { startFrame: number; endFrame: number },
    swapOptions?: { referenceFile?: File; stylePrompt?: string },
  ) => {
    setIsSwapping(true);
    setError(null);
    try {
      if (swapOptions?.referenceFile) {
        await uploadReference(videoId, swapOptions.referenceFile);
      }
      const jid = await startSwap(videoId, selectedIds, {
        ...frameWindow,
        stylePrompt: swapOptions?.stylePrompt,
      });
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
    navigate("/");
  };

  const handleOpenGalleryVideo = async (src: string | File) => {
    try {
      setStep("detecting");
      navigate("/editor");
      let file: File;
      if (typeof src === "string") {
        const response = await fetch(src);
        const blob = await response.blob();
        const filename =
          src.split("/").pop()?.split("?")[0] || "demo-video.mp4";
        file = new File([blob], filename, { type: blob.type || "video/mp4" });
      } else {
        file = src;
      }

      await handleUpload(file);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load demo video");
      setStep("gallery");
    }
  };

  const handleUserUpload = (file: File) => {
    const url = URL.createObjectURL(file);
    setUserVideos((prev) => [...prev, { name: file.name, url, file }]);
  };

  const handleOpenImageFlow = () => {
    setError(null);
    navigate("/image-editor");
  };

  return (
    <div className="relative flex min-h-screen w-full flex-col items-center overflow-hidden bg-[radial-gradient(circle_at_top,_rgba(169,255,131,0.2),transparent_22%),radial-gradient(circle_at_10%_80%,_rgba(255,178,123,0.16),transparent_28%),radial-gradient(circle_at_88%_18%,_rgba(110,138,255,0.18),transparent_26%),linear-gradient(180deg,_#f9fbf6_0%,_#f3f7ff_54%,_#eef3ff_100%)] px-4 py-6 font-sans md:px-8 md:py-8">
      <div className="pointer-events-none absolute -left-20 top-12 h-72 w-72 rounded-full bg-lime-300/24 blur-3xl" />
      <div className="pointer-events-none absolute right-0 top-16 h-80 w-80 rounded-full bg-sky-300/16 blur-3xl" />
      <div className="pointer-events-none absolute bottom-0 left-1/3 h-80 w-80 rounded-full bg-orange-200/18 blur-3xl" />
      <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(135deg,rgba(255,255,255,0.46),transparent_34%,rgba(255,255,255,0.24)_68%,transparent)]" />
      <div className="relative z-10 flex w-full max-w-7xl flex-col items-center">
        {step !== "player" && (
          <div className="mb-10 grid w-full gap-6 rounded-[40px] border border-white/70 bg-white/68 p-6 shadow-[0_36px_110px_rgba(15,23,42,0.10)] backdrop-blur-2xl md:p-8 lg:grid-cols-[1.3fr_0.8fr] lg:items-center">
            <div>
              <div className="mb-4 inline-flex rounded-full border border-black/8 bg-white/78 px-4 py-1.5 text-[11px] font-semibold uppercase tracking-[0.3em] text-slate-500 shadow-[0_10px_30px_rgba(15,23,42,0.05)]">
                VEED Hackathon Build
              </div>
              <h1 className="max-w-3xl bg-[linear-gradient(135deg,#111827_0%,#2b344f_32%,#6b63ff_62%,#62d59a_100%)] bg-clip-text text-5xl font-black tracking-tight text-transparent md:text-6xl">
                Face swapping, but with an editor.
              </h1>
              <p className="mt-4 max-w-2xl text-base leading-7 text-slate-600">
                Upload a short clip, inspect tracked faces, trim the exact
                range, and launch the swap from one polished workspace instead
                of a pile of disconnected steps.
              </p>
              <div className="mt-6 flex flex-wrap gap-3">
                <div className="rounded-full border border-lime-200 bg-lime-50/90 px-4 py-2 text-sm font-semibold text-lime-900 shadow-[0_12px_24px_rgba(157,255,116,0.18)]">
                  Clip-aware editor
                </div>
                <div className="rounded-full border border-sky-200 bg-white/86 px-4 py-2 text-sm font-semibold text-slate-700 shadow-[0_12px_24px_rgba(59,130,246,0.08)]">
                  Live face tracking
                </div>
                <div className="rounded-full border border-violet-200 bg-white/86 px-4 py-2 text-sm font-semibold text-slate-700 shadow-[0_12px_24px_rgba(124,58,237,0.08)]">
                  Async render pipeline
                </div>
              </div>
              <PartnerStrip compact className="mt-6" />
            </div>

            <div className="grid gap-4 md:grid-cols-3 lg:grid-cols-1">
              <div className="rounded-[28px] border border-white/70 bg-[linear-gradient(135deg,rgba(255,255,255,0.92),rgba(248,241,255,0.94))] p-5 shadow-[0_20px_50px_rgba(15,23,42,0.06)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-500">
                  Output
                </div>
                <div className="mt-2 text-2xl font-black tracking-tight text-slate-900">
                  One clean flow
                </div>
                <p className="mt-2 text-sm leading-6 text-slate-600">
                  Selection, preview, render state, and download all stay inside
                  a single product surface.
                </p>
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="mb-6 w-full max-w-lg rounded-2xl border border-red-200 bg-red-50/90 px-4 py-3 text-center text-sm font-medium text-red-700 shadow-[0_16px_36px_rgba(239,68,68,0.10)]">
            {error}
          </div>
        )}

        <Routes>
          <Route
            path="/"
            element={
              <>
                {step === "gallery" && (
                  <Gallery
                    userVideos={userVideos}
                    onSelect={handleOpenGalleryVideo}
                    onUserUpload={handleUserUpload}
                    onImageFlowClick={handleOpenImageFlow}
                  />
                )}

                {step === "upload" && (
                  <div className="w-full max-w-2xl rounded-[32px] border border-white/70 bg-white/70 p-6 shadow-[0_30px_90px_rgba(15,23,42,0.10)] backdrop-blur-xl">
                    <div className="mb-6 flex items-center justify-between">
                      <button
                        onClick={() => setStep("gallery")}
                        className="flex items-center gap-2 rounded-full border border-black/8 bg-white/80 px-4 py-2 text-sm font-medium text-slate-600 transition-colors hover:text-slate-950"
                      >
                        <ArrowLeft className="w-4 h-4" />
                        Back to Gallery
                      </button>
                    </div>
                    <VideoUploader
                      onUpload={handleUpload}
                      isUploading={isUploading}
                    />
                  </div>
                )}
              </>
            }
          />

          <Route
            path="/editor"
            element={
              <>
                {step === "detecting" && (
                  <div className="rounded-[32px] border border-white/70 bg-white/72 px-10 py-10 text-center shadow-[0_30px_90px_rgba(15,23,42,0.08)] backdrop-blur-2xl">
                    <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full border border-lime-200 bg-lime-50 text-slate-900 shadow-[0_18px_36px_rgba(157,255,116,0.18)]">
                      <Loader2 className="h-7 w-7 animate-spin" />
                    </div>
                    <p className="text-lg font-semibold text-slate-900">
                      Analyzing faces...
                    </p>
                    <p className="mt-2 text-sm text-slate-600">
                      Uploading the clip, extracting frames, and preparing the
                      review editor.
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
                  <div className="fixed inset-0 z-50 h-screen w-full">
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
              </>
            }
          />

          <Route path="/image-editor" element={<ImageEditor />} />
        </Routes>
      </div>
    </div>
  );
}

export default App;
