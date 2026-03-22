import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  ArrowLeft,
  Download,
  ImagePlus,
  Loader2,
  RefreshCcw,
  ScanFace,
  Sparkles,
  Upload,
  X,
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import {
  analyzeMediaFaces,
  getJobDownloadUrl,
  getJobStatus,
  startFaceSwapJob,
  uploadReference,
  uploadMedia,
} from "../lib/utils/api";
import type { DetectFacesResponse, StatusResponse } from "../types";
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

export function ImageEditor() {
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const referenceInputRef = useRef<HTMLInputElement>(null);

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [referenceFile, setReferenceFile] = useState<File | null>(null);
  const [stylePrompt, setStylePrompt] = useState("");
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
  const allFacesSelected = faces.length > 0 && selectedFaceIdList.length === faces.length;
  const runwareRequested = !referenceFile && stylePrompt.trim().length > 0;
  const statusWarnings = status?.warnings ?? [];
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
    setReferenceFile(null);
    setStylePrompt("");
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
    if (referenceInputRef.current) {
      referenceInputRef.current.value = "";
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
      setSelectedFaceIds(new Set(detectResponse.faces.map((face) => face.face_id)));
    } catch (uploadError) {
      setError(errorMessage(uploadError, "Image analysis failed"));
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleReferenceFileChange = (file: File | null) => {
    if (!file) {
      return;
    }
    if (!file.type.startsWith("image/") && !SUPPORTED_IMAGE_PATTERN.test(file.name)) {
      setError("Please upload a PNG, JPG, or WebP reference image.");
      return;
    }
    clearSwapState();
    setError(null);
    setReferenceFile(file);
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

  const handleSelectAllFaces = () => {
    clearSwapState();
    setError(null);
    setSelectedFaceIds(
      allFacesSelected ? new Set() : new Set(faces.map((face) => face.face_id)),
    );
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
      warnings: null,
      media_id: mediaId,
      media_type: "image",
    });

    try {
      if (referenceFile) {
        await uploadReference(mediaId, referenceFile);
      }

      const nextJobId = await startFaceSwapJob(mediaId, selectedFaceIdList, {
        stylePrompt: referenceFile ? undefined : stylePrompt.trim() || undefined,
      });
      setJobId(nextJobId);
    } catch (swapError) {
      setStatus({
        status: "failed",
        progress: 0,
        error: errorMessage(swapError, "Image swap failed"),
        warnings: null,
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
  const referenceSetupPanel = (
    <div className="mt-8 rounded-[24px] border border-white/70 bg-white/82 p-5 shadow-[0_20px_50px_rgba(15,23,42,0.08)]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="max-w-2xl">
          <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-500">
            Optional Reference Controls
          </div>
          <h3 className="mt-2 text-xl font-black tracking-tight text-slate-900">
            Upload a reference face or describe one for Runware
          </h3>
          <p className="mt-2 text-sm leading-7 text-slate-600">
            Uploaded reference images take priority. If you leave that empty and
            add a style prompt, the backend will try Runware generation first and
            automatically fall back if it fails. Leave both empty to use the
            configured sample reference. Runware generation still requires a
            server-side `RUNWARE_API_KEY`.
          </p>
        </div>
        <div className="rounded-full border border-slate-200 bg-slate-50/90 px-4 py-2 text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
          Optional
        </div>
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-[0.92fr_1.08fr]">
        <div className="rounded-[24px] border border-slate-200 bg-slate-50/90 p-5">
          <div className="flex items-center gap-2 text-sm font-bold text-slate-900">
            <ImagePlus className="h-4 w-4 text-slate-700" />
            Reference image
          </div>
          <p className="mt-2 text-sm leading-7 text-slate-600">
            Upload a custom source face to override Runware and the server fallback.
          </p>

          <div className="mt-4 flex flex-wrap gap-3">
            <button
              onClick={() => referenceInputRef.current?.click()}
              disabled={showProcessing || isAnalyzing}
              className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 transition-colors hover:text-slate-950"
            >
              <ImagePlus className="h-4 w-4" />
              {referenceFile ? "Change reference" : "Upload reference"}
            </button>

            {referenceFile && (
              <button
                onClick={() => {
                  clearSwapState();
                  setReferenceFile(null);
                  setError(null);
                }}
                disabled={showProcessing || isAnalyzing}
                className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-600 transition-colors hover:text-slate-950"
              >
                <X className="h-4 w-4" />
                Remove reference
              </button>
            )}
          </div>

          <div className="mt-4 min-h-12 rounded-[20px] border border-dashed border-slate-300 bg-white/75 px-4 py-3 text-sm text-slate-600">
            {referenceFile ? (
              <span className="font-medium text-slate-900">{referenceFile.name}</span>
            ) : (
              "No uploaded reference image selected."
            )}
          </div>
        </div>

        <div className="rounded-[24px] border border-slate-200 bg-slate-50/90 p-5">
          <div className="flex items-center justify-between gap-3">
            <div className="text-sm font-bold text-slate-900">Runware style prompt</div>
            <div className="rounded-full border border-slate-200 bg-white px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">
              {referenceFile ? "Disabled while reference image is uploaded" : "Optional"}
            </div>
          </div>
          <p className="mt-2 text-sm leading-7 text-slate-600">
            Describe the generated face only when you want Runware to create one.
            If this fails, the server will fall back and report the warning here.
          </p>
          <textarea
            value={stylePrompt}
            onChange={(event) => {
              clearSwapState();
              setStylePrompt(event.target.value);
              setError(null);
            }}
            disabled={Boolean(referenceFile) || showProcessing}
            maxLength={200}
            rows={4}
            placeholder="Example: wearing aviator sunglasses and subtle face paint"
            className="mt-4 w-full rounded-[20px] border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-slate-400 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400"
          />
          <div className="mt-3 flex items-center justify-between gap-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
            <span>{referenceFile ? "Ignored because a reference image is uploaded" : "Leave blank to skip Runware and use fallback"}</span>
            <span>{stylePrompt.trim().length}/200</span>
          </div>
        </div>
      </div>
    </div>
  );

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
          {referenceFile
            ? "Using uploaded reference face"
            : runwareRequested
              ? "Runware reference generation enabled"
              : "Using server fallback reference"}
        </div>
      </div>

      <div className="mb-8 max-w-3xl">
        <h2 className="text-3xl font-black tracking-tight text-slate-900 md:text-4xl">
          Image Face Swap Studio
        </h2>
        <p className="mt-3 text-sm leading-7 text-slate-600 md:text-base">
          Upload a still image, analyze the detected faces, click the face boxes
          directly to choose what to swap, and render a downloadable result from
          the same editor.
        </p>
      </div>

      <input
        ref={referenceInputRef}
        type="file"
        accept=".png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp"
        className="hidden"
        onChange={(event) => {
          handleReferenceFileChange(event.target.files?.[0] ?? null);
          event.target.value = "";
        }}
      />

      {error && (
        <div className="mb-6 flex items-start gap-3 rounded-[24px] border border-red-200 bg-red-50/95 px-5 py-4 text-sm text-red-700 shadow-[0_16px_36px_rgba(239,68,68,0.10)]">
          <AlertCircle className="mt-0.5 h-5 w-5 shrink-0" />
          <p>{error}</p>
        </div>
      )}

      {statusWarnings.length > 0 && (
        <div className="mb-6 flex items-start gap-3 rounded-[24px] border border-amber-200 bg-amber-50/95 px-5 py-4 text-sm text-amber-900 shadow-[0_16px_36px_rgba(245,158,11,0.12)]">
          <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-amber-700" />
          <div className="space-y-1">
            <p className="font-semibold">Reference generation warning</p>
            {statusWarnings.map((warning) => (
              <p key={warning}>{warning}</p>
            ))}
          </div>
        </div>
      )}

      <div className="grid gap-8 lg:grid-cols-[1.15fr_0.85fr]">
        <div className="flex flex-col gap-4">
          <div className="flex items-center justify-between gap-4">
            <div>
              <div className="text-sm font-bold text-slate-900">Target image</div>
              <p className="mt-1 text-sm text-slate-600">
                Upload the image that should receive the swap, then click the
                face boxes directly to control the selection.
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
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-[22px] border border-slate-200 bg-white/88 px-4 py-3">
                <div>
                  <div className="text-sm font-semibold text-slate-900">Face selection</div>
                  <p className="mt-1 text-sm text-slate-600">
                    Click faces in the preview to include or remove them from the swap.
                  </p>
                </div>
                {faces.length > 0 && (
                  <button
                    onClick={handleSelectAllFaces}
                    disabled={showProcessing || isAnalyzing}
                    className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 transition-colors hover:text-slate-950"
                  >
                    {allFacesSelected ? "Deselect all" : "Select all"}
                  </button>
                )}
              </div>

              <div className="relative aspect-square overflow-hidden rounded-[28px] border-2 border-slate-200 bg-[linear-gradient(135deg,rgba(255,255,255,0.68),rgba(244,247,255,0.92))]">
                <TrackedImagePreview
                  src={previewUrl}
                  faces={faces}
                  selectedFaceIds={selectedFaceIdList}
                  imageWidth={detection?.width}
                  imageHeight={detection?.height}
                  className="h-full w-full"
                  onFaceClick={toggleFace}
                  disabled={showProcessing || isAnalyzing}
                />
                <div className="pointer-events-none absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/60 to-transparent px-5 py-5">
                  <div className="flex flex-wrap items-center gap-2 text-xs font-semibold uppercase tracking-[0.2em] text-white/88">
                    <span>{selectedFile?.name ?? "target image"}</span>
                    {dimensionsLabel && <span>{dimensionsLabel}</span>}
                    {faces.length > 0 && <span>{faces.length} faces</span>}
                    {selectedFaceIdList.length > 0 && <span>{selectedFaceIdList.length} selected</span>}
                  </div>
                </div>
              </div>
            </>
          ) : (
            <button
              type="button"
              className="group relative flex aspect-square w-full items-center justify-center overflow-hidden rounded-[28px] border-2 border-dashed border-slate-300 bg-[linear-gradient(135deg,rgba(255,255,255,0.68),rgba(244,247,255,0.92))] text-left transition-all hover:border-slate-400"
              onClick={() => inputRef.current?.click()}
              disabled={showProcessing || isAnalyzing}
            >
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
            </button>
          )}
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

      {referenceSetupPanel}

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
          {faces.length > 0 ? "Re-analyze image" : "Upload and analyze image"}
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
          {referenceFile && (
            <div className="rounded-full border border-slate-200 bg-white/88 px-3 py-1.5">
              Custom reference uploaded
            </div>
          )}
          {!referenceFile && runwareRequested && (
            <div className="rounded-full border border-slate-200 bg-white/88 px-3 py-1.5">
              Runware requested
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
    </div>
  );
}
