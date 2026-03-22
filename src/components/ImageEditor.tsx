import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  ArrowLeft,
  Download,
  Loader2,
  RefreshCcw,
  ScanFace,
  Sparkles,
  Upload,
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import {
  analyzeMediaFaces,
  getJobDownloadUrl,
  getJobStatus,
  startFaceSwapJob,
  uploadMedia,
} from "../lib/utils/api";
import type { DetectFacesResponse, FaceInfo, StatusResponse } from "../types";
import { TrackedImagePreview } from "./TrackedImagePreview";

const SUPPORTED_IMAGE_PATTERN = /\.(png|jpe?g|webp)$/i;

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function phaseLabel(status: StatusResponse | null): string {
  if (!status) {
    return "Ready";
  }
  if (status.phase === "extracting_clips") {
    return "Preparing selection";
  }
  if (status.phase === "swapping") {
    return "Swapping faces";
  }
  if (status.phase === "compositing") {
    return "Compositing image";
  }
  if (status.phase === "rendering") {
    return "Rendering image";
  }
  if (status.phase === "failed") {
    return "Swap failed";
  }
  if (status.phase === "completed") {
    return "Swap complete";
  }
  return "Processing";
}

function frameSummary(face: FaceInfo): string {
  return face.frame_count === 1 ? "1 frame" : `${face.frame_count} frames`;
}

export function ImageEditor() {
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [mediaId, setMediaId] = useState<string | null>(null);
  const [detection, setDetection] = useState<DetectFacesResponse | null>(null);
  const [selectedFaceIds, setSelectedFaceIds] = useState<Set<string>>(new Set());
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isStartingSwap, setIsStartingSwap] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedFile) {
      setPreviewUrl(null);
      return undefined;
    }

    const url = URL.createObjectURL(selectedFile);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [selectedFile]);

  useEffect(() => {
    if (!jobId) {
      return undefined;
    }

    let active = true;
    let intervalId = 0;

    const poll = async () => {
      try {
        const nextStatus = await getJobStatus(jobId);
        if (!active) {
          return;
        }
        setStatus(nextStatus);
        if (nextStatus.status !== "processing" && intervalId) {
          window.clearInterval(intervalId);
        }
      } catch {
        // Ignore transient polling errors and continue retrying.
      }
    };

    void poll();
    intervalId = window.setInterval(() => {
      void poll();
    }, 1000);

    return () => {
      active = false;
      if (intervalId) {
        window.clearInterval(intervalId);
      }
    };
  }, [jobId]);

  const faces = detection?.faces ?? [];
  const selectedFaceIdList = useMemo(
    () => Array.from(selectedFaceIds),
    [selectedFaceIds],
  );
  const downloadUrl = jobId ? getJobDownloadUrl(jobId) : null;
  const hasResult = Boolean(downloadUrl && status?.status === "completed");
  const showProcessing = isStartingSwap || status?.status === "processing";
  const progressPercent = Math.round((status?.progress ?? 0) * 100);

  const clearSwapState = () => {
    setJobId(null);
    setStatus(null);
  };

  const resetEditor = () => {
    setSelectedFile(null);
    setPreviewUrl(null);
    setMediaId(null);
    setDetection(null);
    setSelectedFaceIds(new Set());
    clearSwapState();
    setIsAnalyzing(false);
    setIsStartingSwap(false);
    setError(null);
    if (inputRef.current) {
      inputRef.current.value = "";
    }
  };

  const handleFileChange = (file: File | null) => {
    if (!file) {
      return;
    }

    if (!file.type.startsWith("image/") && !SUPPORTED_IMAGE_PATTERN.test(file.name)) {
      setError("Please upload a PNG, JPG, or WebP image.");
      return;
    }

    setSelectedFile(file);
    setMediaId(null);
    setDetection(null);
    setSelectedFaceIds(new Set());
    clearSwapState();
    setError(null);
  };

  const handleAnalyze = async () => {
    if (!selectedFile || isAnalyzing) {
      return;
    }

    setIsAnalyzing(true);
    setError(null);
    clearSwapState();

    try {
      const upload = await uploadMedia(selectedFile);
      if (upload.media_type !== "image") {
        throw new Error("The backend did not accept this upload as an image.");
      }

      const detectResponse = await analyzeMediaFaces(upload.media_id);
      if (detectResponse.media_type !== "image") {
        throw new Error("The backend returned a non-image analysis response.");
      }

      setMediaId(upload.media_id);
      setDetection(detectResponse);
      setSelectedFaceIds(new Set());
    } catch (uploadError) {
      setError(errorMessage(uploadError, "Image analysis failed"));
    } finally {
      setIsAnalyzing(false);
    }
  };

  const toggleFace = (faceId: string) => {
    clearSwapState();
    setError(null);
    setSelectedFaceIds((current) => {
      const next = new Set(current);
      if (next.has(faceId)) {
        next.delete(faceId);
      } else {
        next.add(faceId);
      }
      return next;
    });
  };

  const handleSwap = async () => {
    if (!mediaId || selectedFaceIdList.length === 0 || isStartingSwap) {
      return;
    }

    setIsStartingSwap(true);
    setError(null);
    setStatus({
      status: "processing",
      progress: 0,
      error: null,
      media_id: mediaId,
      media_type: "image",
    });

    try {
      const nextJobId = await startFaceSwapJob(mediaId, selectedFaceIdList);
      setJobId(nextJobId);
    } catch (swapError) {
      setStatus({
        status: "failed",
        progress: 0,
        error: errorMessage(swapError, "Image swap failed"),
        media_id: mediaId,
        media_type: "image",
      });
      setError(errorMessage(swapError, "Image swap failed"));
    } finally {
      setIsStartingSwap(false);
    }
  };

  const dimensionsLabel =
    detection?.width && detection?.height
      ? `${detection.width} x ${detection.height}`
      : null;

  return (
    <div className="w-full max-w-6xl rounded-[32px] border border-white/70 bg-white/70 p-6 shadow-[0_30px_90px_rgba(15,23,42,0.10)] backdrop-blur-xl md:p-10">
      <div className="mb-8 flex flex-wrap items-center justify-between gap-4">
        <button
          onClick={() => navigate("/")}
          className="flex items-center gap-2 rounded-full border border-black/8 bg-white/80 px-4 py-2 text-sm font-medium text-slate-600 transition-colors hover:text-slate-950"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Gallery
        </button>

        <div className="rounded-full border border-lime-200 bg-lime-50/90 px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-lime-950">
          Uses configured server reference face
        </div>
      </div>

      <div className="mb-8 max-w-3xl">
        <h2 className="text-3xl font-black tracking-tight text-slate-900 md:text-4xl">
          Image Face Swap Studio
        </h2>
        <p className="mt-3 text-sm leading-7 text-slate-600 md:text-base">
          Upload a still image, inspect the detected faces, choose exactly which
          ones to swap, and render a downloadable result from the same editor.
        </p>
      </div>

      {error && (
        <div className="mb-6 flex items-start gap-3 rounded-[24px] border border-red-200 bg-red-50/95 px-5 py-4 text-sm text-red-700 shadow-[0_16px_36px_rgba(239,68,68,0.10)]">
          <AlertCircle className="mt-0.5 h-5 w-5 shrink-0" />
          <p>{error}</p>
        </div>
      )}

      <div className="grid gap-8 lg:grid-cols-[1.15fr_0.85fr]">
        <div className="flex flex-col gap-4">
          <div className="flex items-center justify-between gap-4">
            <div>
              <div className="text-sm font-bold text-slate-900">Target image</div>
              <p className="mt-1 text-sm text-slate-600">
                Upload the image that should receive the swap.
              </p>
            </div>
            {selectedFile && (
              <button
                onClick={() => inputRef.current?.click()}
                disabled={showProcessing || isAnalyzing}
                className="rounded-full border border-slate-200 bg-white/90 px-4 py-2 text-sm font-medium text-slate-700 transition-colors hover:text-slate-950"
              >
                Change image
              </button>
            )}
          </div>

          <button
            type="button"
            className="group relative flex aspect-square w-full items-center justify-center overflow-hidden rounded-[28px] border-2 border-dashed border-slate-300 bg-[linear-gradient(135deg,rgba(255,255,255,0.68),rgba(244,247,255,0.92))] text-left transition-all hover:border-slate-400"
            onClick={() => inputRef.current?.click()}
            disabled={showProcessing || isAnalyzing}
          >
            <input
              ref={inputRef}
              type="file"
              accept=".png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp"
              className="hidden"
              onChange={(event) => {
                handleFileChange(event.target.files?.[0] ?? null);
                event.target.value = "";
              }}
            />

            {previewUrl ? (
              <>
                <TrackedImagePreview
                  src={previewUrl}
                  faces={faces}
                  selectedFaceIds={selectedFaceIdList}
                  imageWidth={detection?.width}
                  imageHeight={detection?.height}
                  className="h-full w-full"
                />
                <div className="pointer-events-none absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/60 to-transparent px-5 py-5">
                  <div className="flex flex-wrap items-center gap-2 text-xs font-semibold uppercase tracking-[0.2em] text-white/88">
                    <span>{selectedFile?.name ?? "target image"}</span>
                    {dimensionsLabel && <span>{dimensionsLabel}</span>}
                    {faces.length > 0 && <span>{faces.length} faces</span>}
                  </div>
                </div>
              </>
            ) : (
              <div className="flex max-w-sm flex-col items-center gap-4 p-8 text-center text-slate-500 transition-colors group-hover:text-slate-700">
                <div className="rounded-full border border-slate-200 bg-white/88 p-5 text-slate-700 shadow-[0_12px_24px_rgba(15,23,42,0.08)]">
                  <Upload className="h-8 w-8" />
                </div>
                <div>
                  <div className="text-lg font-bold tracking-tight text-slate-900">
                    Upload target image
                  </div>
                  <p className="mt-2 text-sm leading-7 text-slate-600">
                    JPG, PNG, or WebP. The editor will detect faces directly on
                    the uploaded still image.
                  </p>
                </div>
              </div>
            )}
          </button>
        </div>

        <div className="flex flex-col gap-4">
          <div>
            <div className="text-sm font-bold text-slate-900">Result</div>
            <p className="mt-1 text-sm text-slate-600">
              The swapped image will appear here after the job finishes.
            </p>
          </div>

          <div className="flex aspect-square flex-col overflow-hidden rounded-[28px] border border-white/70 bg-[linear-gradient(135deg,rgba(255,255,255,0.9),rgba(241,247,255,0.94))] shadow-[0_24px_60px_rgba(15,23,42,0.08)]">
            {hasResult && downloadUrl ? (
              <>
                <img
                  src={downloadUrl}
                  alt="Swapped result"
                  className="h-full w-full object-contain bg-slate-950"
                />
                <div className="border-t border-slate-200/80 bg-white/90 px-5 py-4">
                  <div className="mb-3 text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
                    {status?.output_filename ?? "swapped image"}
                  </div>
                  <div className="flex flex-wrap gap-3">
                    <a
                      href={downloadUrl}
                      download={status?.output_filename ?? "swapped-image.png"}
                      className="inline-flex items-center gap-2 rounded-full bg-[linear-gradient(135deg,#111827_0%,#2b344f_100%)] px-5 py-2.5 text-sm font-semibold text-white shadow-[0_12px_24px_rgba(15,23,42,0.16)] transition-transform hover:-translate-y-0.5"
                    >
                      <Download className="h-4 w-4" />
                      Download result
                    </a>
                    <button
                      onClick={resetEditor}
                      className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white/90 px-5 py-2.5 text-sm font-semibold text-slate-700 transition-colors hover:text-slate-950"
                    >
                      <RefreshCcw className="h-4 w-4" />
                      New image
                    </button>
                  </div>
                </div>
              </>
            ) : (
              <div className="flex h-full flex-col items-center justify-center gap-5 px-8 py-8 text-center">
                {showProcessing ? (
                  <>
                    <div className="flex h-16 w-16 items-center justify-center rounded-full border border-lime-200 bg-lime-50 text-slate-900 shadow-[0_18px_36px_rgba(157,255,116,0.18)]">
                      <Loader2 className="h-8 w-8 animate-spin" />
                    </div>
                    <div>
                      <div className="text-lg font-bold tracking-tight text-slate-900">
                        {isStartingSwap ? "Starting image swap" : phaseLabel(status)}
                      </div>
                      <p className="mt-2 text-sm leading-7 text-slate-600">
                        {status?.message ?? "Running the swap pipeline on the selected faces."}
                      </p>
                    </div>
                    <div className="w-full max-w-xs">
                      <div className="h-3 overflow-hidden rounded-full bg-slate-200">
                        <div
                          className="h-full rounded-full bg-[linear-gradient(135deg,#111827_0%,#62d59a_100%)] transition-all duration-500"
                          style={{ width: `${progressPercent}%` }}
                        />
                      </div>
                      <div className="mt-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
                        {progressPercent}% complete
                      </div>
                    </div>
                  </>
                ) : status?.status === "failed" ? (
                  <>
                    <div className="flex h-16 w-16 items-center justify-center rounded-full border border-red-200 bg-red-50 text-red-700 shadow-[0_18px_36px_rgba(239,68,68,0.12)]">
                      <AlertCircle className="h-8 w-8" />
                    </div>
                    <div>
                      <div className="text-lg font-bold tracking-tight text-slate-900">
                        Swap failed
                      </div>
                      <p className="mt-2 text-sm leading-7 text-slate-600">
                        {status.error ?? "The backend could not render this image swap."}
                      </p>
                    </div>
                  </>
                ) : (
                  <>
                    <div className="flex h-16 w-16 items-center justify-center rounded-full border border-slate-200 bg-white/90 text-slate-700 shadow-[0_12px_24px_rgba(15,23,42,0.08)]">
                      <Sparkles className="h-8 w-8" />
                    </div>
                    <div>
                      <div className="text-lg font-bold tracking-tight text-slate-900">
                        Ready for output
                      </div>
                      <p className="mt-2 text-sm leading-7 text-slate-600">
                        Detect faces in the target image, choose the people you
                        want to swap, and the rendered result will appear here.
                      </p>
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="mt-8 flex flex-wrap items-center gap-3">
        <button
          onClick={() => inputRef.current?.click()}
          disabled={showProcessing || isAnalyzing}
          className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white/90 px-5 py-3 text-sm font-semibold text-slate-700 transition-colors hover:text-slate-950"
        >
          <Upload className="h-4 w-4" />
          {selectedFile ? "Choose another image" : "Choose image"}
        </button>

        <button
          onClick={handleAnalyze}
          disabled={!selectedFile || isAnalyzing || isStartingSwap}
          className="inline-flex items-center gap-2 rounded-full bg-[linear-gradient(135deg,#111827_0%,#2b344f_100%)] px-5 py-3 text-sm font-semibold text-white shadow-[0_12px_24px_rgba(15,23,42,0.16)] transition-transform hover:-translate-y-0.5 disabled:pointer-events-none disabled:opacity-50"
        >
          {isAnalyzing ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <ScanFace className="h-4 w-4" />
          )}
          {faces.length > 0 ? "Re-analyze image" : "Upload and detect faces"}
        </button>

        <button
          onClick={handleSwap}
          disabled={
            !mediaId ||
            selectedFaceIdList.length === 0 ||
            isAnalyzing ||
            isStartingSwap ||
            status?.status === "processing"
          }
          className="inline-flex items-center gap-2 rounded-full border border-slate-900 bg-slate-900 px-5 py-3 text-sm font-semibold text-white transition-transform hover:-translate-y-0.5 disabled:pointer-events-none disabled:opacity-50"
        >
          <Sparkles className="h-4 w-4" />
          Swap {selectedFaceIdList.length || ""} {selectedFaceIdList.length === 1 ? "face" : "faces"}
        </button>

        {selectedFile && (
          <button
            onClick={resetEditor}
            disabled={showProcessing || isAnalyzing}
            className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white/90 px-5 py-3 text-sm font-semibold text-slate-700 transition-colors hover:text-slate-950"
          >
            <RefreshCcw className="h-4 w-4" />
            Reset editor
          </button>
        )}
      </div>

      {(selectedFile || faces.length > 0) && (
        <div className="mt-8 flex flex-wrap gap-3 text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
          {selectedFile && (
            <div className="rounded-full border border-slate-200 bg-white/88 px-3 py-1.5">
              {selectedFile?.name ?? "target image"}
            </div>
          )}
          {dimensionsLabel && (
            <div className="rounded-full border border-slate-200 bg-white/88 px-3 py-1.5">
              {dimensionsLabel}
            </div>
          )}
          {detection && (
            <div className="rounded-full border border-slate-200 bg-white/88 px-3 py-1.5">
              {faces.length} faces detected
            </div>
          )}
          {selectedFaceIdList.length > 0 && (
            <div className="rounded-full border border-slate-200 bg-white/88 px-3 py-1.5">
              {selectedFaceIdList.length} selected
            </div>
          )}
        </div>
      )}

      {detection && faces.length === 0 && (
        <div className="mt-8 rounded-[28px] border border-slate-200 bg-white/90 px-6 py-8 text-center shadow-[0_18px_42px_rgba(15,23,42,0.05)]">
          <div className="text-lg font-bold tracking-tight text-slate-900">
            No faces detected
          </div>
          <p className="mt-2 text-sm leading-7 text-slate-600">
            Try a different image with a clearer frontal face, then run detection
            again.
          </p>
        </div>
      )}

      {faces.length > 0 && (
        <div className="mt-8 rounded-[30px] border border-white/70 bg-white/82 p-6 shadow-[0_24px_60px_rgba(15,23,42,0.08)]">
          <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-500">
                Face Review
              </div>
              <h3 className="mt-2 text-2xl font-black tracking-tight text-slate-900">
                Choose the faces to swap
              </h3>
              <p className="mt-2 text-sm leading-7 text-slate-600">
                Click each detected face to include or remove it from the image
                swap job.
              </p>
            </div>
            <div className="rounded-full border border-slate-200 bg-slate-50/90 px-4 py-2 text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
              {selectedFaceIdList.length} selected of {faces.length}
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {faces.map((face) => {
              const isSelected = selectedFaceIds.has(face.face_id);

              return (
                <button
                  key={face.face_id}
                  onClick={() => toggleFace(face.face_id)}
                  disabled={showProcessing || isAnalyzing}
                  className={`group overflow-hidden rounded-[24px] border text-left transition-all ${
                    isSelected
                      ? "border-slate-900 bg-slate-950 text-white shadow-[0_20px_40px_rgba(15,23,42,0.16)]"
                      : "border-slate-200 bg-white hover:-translate-y-0.5 hover:border-slate-300 hover:shadow-[0_20px_40px_rgba(15,23,42,0.10)]"
                  }`}
                >
                  <div className="relative aspect-[4/3] overflow-hidden bg-slate-950">
                    <img
                      src={face.thumbnail}
                      alt={`Detected ${face.face_id}`}
                      className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-[1.03]"
                    />
                    <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent px-4 py-4">
                      <div className="flex flex-wrap gap-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-white/90">
                        <span>{face.face_id}</span>
                        <span>{face.gender || "unknown"}</span>
                        <span>{face.age || "?"}y</span>
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center justify-between gap-3 px-4 py-4">
                    <div>
                      <div className={`text-sm font-bold ${isSelected ? "text-white" : "text-slate-900"}`}>
                        {isSelected ? "Included in swap" : "Not selected"}
                      </div>
                      <div className={`mt-1 text-sm ${isSelected ? "text-white/75" : "text-slate-600"}`}>
                        {frameSummary(face)}
                      </div>
                    </div>
                    <div
                      className={`rounded-full px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] ${
                        isSelected
                          ? "bg-white/14 text-white"
                          : "bg-slate-100 text-slate-500"
                      }`}
                    >
                      {isSelected ? "Selected" : "Click to select"}
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
