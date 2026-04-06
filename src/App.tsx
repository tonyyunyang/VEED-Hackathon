import { useEffect, useRef, useState, useCallback } from "react";
import { Routes, Route, useNavigate, useLocation } from "react-router-dom";
import "./App.css";
import "./index.css";
import type { AppStep, FaceInfo } from "./types";
import {
  detectFaces,
  uploadVideo,
  startSwap,
  uploadReference,
  reAnalyze,
  getDownloadUrl,
  getStatus,
  deleteJob,
} from "./lib/utils/api";
import type { StatusResponse } from "./types";
import { VideoUploader } from "./components/VideoUploader";
import { Gallery } from "./components/Gallery";
import { VideoPlayer } from "./components/VideoPlayer";
import { ImageEditor } from "./components/ImageEditor";
import { PartnerStrip } from "./components/PartnerStrip";
import { ArrowLeft, AlertCircle } from "lucide-react";
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogClose,
} from "./components/ui/alert-dialog";
import { Button } from "./components/ui/button";

/**
 * Ensures a promise takes at least minMs to resolve.
 */
async function withMinDelay<T>(promise: Promise<T>, minMs: number): Promise<T> {
  const [result] = await Promise.all([
    promise,
    new Promise((resolve) => setTimeout(resolve, minMs)),
  ]);
  return result;
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function App() {
  const [step, setStep] = useState<AppStep>("gallery");
  const [videoId, setVideoId] = useState("");
  const [selectedVideoSrc, setSelectedVideoSrc] = useState<string>("");
  const [faces, setFaces] = useState<FaceInfo[]>([]);
  const [detectionFps, setDetectionFps] = useState(0);
  const [swapJobId, setSwapJobId] = useState("");
  const [resultJobId, setResultJobId] = useState("");
  const [swapStatus, setSwapStatus] = useState<StatusResponse | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isSwapping, setIsSwapping] = useState(false);
  const [isAnalyzingFaces, setIsAnalyzingFaces] = useState(false);
  const [isResult, setIsResult] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [userVideos, setUserVideos] = useState<
    { name: string; url: string; file: File }[]
  >([]);
  const uploadedPreviewUrlRef = useRef<string | null>(null);
  const uploadInFlightRef = useRef(false);
  const navigate = useNavigate();
  const location = useLocation();
  const showMarketingHero =
    location.pathname !== "/image-editor" &&
    !location.pathname.startsWith("/processing") &&
    step !== "player";

  const clearUploadedPreview = () => {
    if (uploadedPreviewUrlRef.current) {
      URL.revokeObjectURL(uploadedPreviewUrlRef.current);
      uploadedPreviewUrlRef.current = null;
    }
  };

  useEffect(() => clearUploadedPreview, []);

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [location.pathname]);

  // Polling for swap status
  useEffect(() => {
    if (!isSwapping || !swapJobId) return;

    let active = true;
    const poll = async () => {
      try {
        const s = await getStatus(swapJobId);
        if (!active) return;
        setSwapStatus(s);

        if (s.status === "completed") {
          const downloadUrl = getDownloadUrl(swapJobId);
          
          // Rotational Cleanup: Only one result is active at a time to keep the session light
          if (resultJobId && resultJobId !== swapJobId) {
            void deleteJob(resultJobId);
          }

          setSelectedVideoSrc(downloadUrl);
          setIsResult(true);
          setResultJobId(swapJobId);
          setIsSwapping(false);
          setSwapStatus(null);
          setSwapJobId("");
        } else if (s.status === "failed") {
          setError(s.error || "Swap processing failed");
          setIsSwapping(false);
          setSwapStatus(null);
          setSwapJobId("");
        }
      } catch {
        // Transient error, keep polling
      }
    };

    void poll();
    const interval = setInterval(poll, 1000);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, [isSwapping, swapJobId, resultJobId]);

  // Unified Analysis Workflow
  const runAnalysisWorkflow = useCallback(
    async ({
      src,
      mediaIdProvider,
      onErrorStep = "gallery",
    }: {
      src: string;
      mediaIdProvider: () => Promise<string>;
      onErrorStep?: AppStep;
    }) => {
      if (uploadInFlightRef.current) return;
      uploadInFlightRef.current = true;
      setError(null);
      setFaces([]);
      setDetectionFps(0);
      setSwapJobId("");
      setResultJobId("");
      setSwapStatus(null);
      setIsResult(false);
      setSelectedVideoSrc(src);
      setIsAnalyzingFaces(true);
      setStep("player");
      if (location.pathname !== "/editor") {
        navigate("/editor");
      }

      try {
        const mid = await mediaIdProvider();
        setVideoId(mid);
        const detection = await withMinDelay(detectFaces(mid), 800);
        setDetectionFps(detection.fps);
        setFaces(detection.faces);
      } catch (e) {
        setError(errorMessage(e, "Analysis failed"));
        setStep(onErrorStep);
        if (location.pathname !== "/") {
          navigate("/");
        }
      } finally {
        uploadInFlightRef.current = false;
        setIsUploading(false);
        setIsAnalyzingFaces(false);
      }
    },
    [location.pathname, navigate],
  );

  // Sync route and step state
  useEffect(() => {
    if (location.pathname === "/" && step !== "gallery" && step !== "upload") {
      setStep("gallery");
    } else if (
      location.pathname.startsWith("/editor") &&
      !selectedVideoSrc &&
      step !== "detecting" &&
      step !== "player"
    ) {
      navigate("/", { replace: true });
    }
  }, [location.pathname, step, selectedVideoSrc, navigate]);

  const handleUpload = async (file: File) => {
    const url = URL.createObjectURL(file);
    uploadedPreviewUrlRef.current = url;
    setIsUploading(true);
    await runAnalysisWorkflow({
      src: url,
      mediaIdProvider: () => uploadVideo(file),
      onErrorStep: "upload",
    });
  };

  const handleSwap = async (
    selectedIds: string[],
    frameWindow?: { startFrame: number; endFrame: number },
    swapOptions?: { referenceFile?: File; stylePrompt?: string },
  ) => {
    setIsSwapping(true);
    setError(null);
    setResultJobId("");
    setSwapStatus({
      status: "processing",
      progress: 0,
      error: null,
      warnings: null,
    });
    try {
      if (swapOptions?.referenceFile) {
        await uploadReference(videoId, swapOptions.referenceFile);
      }
      const jid = await startSwap(videoId, selectedIds, {
        ...frameWindow,
        stylePrompt: swapOptions?.stylePrompt,
      });
      setSwapJobId(jid);
    } catch (e) {
      setError(errorMessage(e, "Swap failed"));
      setIsSwapping(false);
      setSwapStatus(null);
    }
  };

  const handleStartOver = () => {
    if (resultJobId) {
      void deleteJob(resultJobId);
    }
    
    clearUploadedPreview();
    setStep("gallery");
    setVideoId("");
    setSelectedVideoSrc("");
    setFaces([]);
    setDetectionFps(0);
    setSwapJobId("");
    setResultJobId("");
    setSwapStatus(null);
    setIsResult(false);
    setError(null);
    navigate("/");
  };

  const handleOpenGalleryVideo = async (src: string | File) => {
    if (src instanceof File) {
      await handleUpload(src);
      return;
    }

    try {
      const response = await fetch(src);
      const blob = await response.blob();
      const filename =
        src.split("/").pop()?.split("?")[0] || "project-video.mp4";
      const file = new File([blob], filename, {
        type: blob.type || "video/mp4",
      });
      await handleUpload(file);
    } catch (e) {
      setError(errorMessage(e, "Failed to load project video"));
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

  const handleEditResult = async (completedJobId: string) => {
    setIsUploading(true);
    await runAnalysisWorkflow({
      src: getDownloadUrl(completedJobId),
      mediaIdProvider: async () => {
        const { media_id } = await reAnalyze(completedJobId);
        return media_id;
      },
      onErrorStep: "gallery",
    });
  };

  return (
    <div className="relative flex min-h-screen w-full flex-col items-center overflow-hidden bg-[radial-gradient(circle_at_top,_rgba(169,255,131,0.2),transparent_22%),radial-gradient(circle_at_10%_80%,_rgba(255,178,123,0.16),transparent_28%),radial-gradient(circle_at_88%_18%,_rgba(110,138,255,0.18),transparent_26%),linear-gradient(180deg,_#f9fbf6_0%,_#f3f7ff_54%,_#eef3ff_100%)] px-4 py-6 font-sans md:px-8 md:py-8">
      <div className="pointer-events-none absolute -left-20 top-12 h-72 w-72 rounded-full bg-lime-300/24 blur-3xl" />
      <div className="pointer-events-none absolute right-0 top-16 h-80 w-80 rounded-full bg-sky-300/16 blur-3xl" />
      <div className="pointer-events-none absolute bottom-0 left-1/3 h-80 w-80 rounded-full bg-orange-200/18 blur-3xl" />
      <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(135deg,rgba(255,255,255,0.46),transparent_34%,rgba(255,255,255,0.24)_68%,transparent)]" />
      <div className="relative z-10 flex w-full max-w-7xl flex-col items-center">
        {showMarketingHero && (
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
                range, and launch the swap from one polished workspace. No more
                disconnected steps.
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
                  Selection, preview, render state, and download.
                </p>
              </div>
            </div>
          </div>
        )}

        <AlertDialog open={!!error} onOpenChange={() => setError(null)}>
          <AlertDialogContent>
            <AlertDialogHeader className="flex flex-col items-center sm:items-center text-center sm:text-center">
              <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-red-100 text-red-600">
                <AlertCircle className="h-10 w-10" />
              </div>
              <AlertDialogTitle className="text-2xl font-black text-slate-900">
                Processing Error
              </AlertDialogTitle>
              <AlertDialogDescription className="mt-2 text-base text-slate-600">
                {error}
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter className="sm:justify-center">
              <AlertDialogClose
                render={
                  <Button variant="outline" className="min-w-32 rounded-xl" />
                }
              >
                Dismiss
              </AlertDialogClose>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>

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
                {(step === "player" || isResult) && (
                  <div className="fixed inset-0 z-50 h-screen w-full">
                    <VideoPlayer
                      videoSrc={selectedVideoSrc}
                      faces={faces}
                      fps={detectionFps}
                      useLiveTracking={Boolean(videoId)}
                      error={error}
                      isSwapping={isSwapping}
                      isAnalyzingFaces={isAnalyzingFaces}
                      isResult={isResult}
                      swapStatus={swapStatus}
                      resultJobId={resultJobId}
                      onSwap={videoId ? handleSwap : undefined}
                      onBack={handleStartOver}
                      onEditAgain={
                        isResult && resultJobId
                          ? () => handleEditResult(resultJobId)
                          : undefined
                      }
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
