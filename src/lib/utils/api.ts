import type {
  DetectFacesResponse,
  StatusResponse,
  SwapResponse,
  UploadMediaResponse,
} from "../../types";

function getApiBaseUrl(): string {
  const configured = getBackendUrl();
  if (configured) {
    return configured;
  }
  if (import.meta.env.DEV) {
    return "http://127.0.0.1:8000";
  }
  return "";
}

function apiUrl(path: string): string {
  const baseUrl = getApiBaseUrl();
  return baseUrl ? `${baseUrl}${path}` : path;
}

async function getErrorMessage(
  res: Response,
  fallback: string,
): Promise<string> {
  try {
    const payload = await res.json();
    if (typeof payload?.detail === "string" && payload.detail.trim()) {
      return payload.detail;
    }
    if (typeof payload?.error === "string" && payload.error.trim()) {
      return payload.error;
    }
  } catch {
    // Fall back to the HTTP status text when the response is not JSON.
  }

  const statusText = res.statusText?.trim();
  return statusText ? `${fallback}: ${statusText}` : fallback;
}

async function requestApi(
  path: string,
  init: RequestInit,
  fallback: string,
): Promise<Response> {
  try {
    const res = await fetch(apiUrl(path), init);
    if (!res.ok) {
      throw new Error(await getErrorMessage(res, fallback));
    }
    return res;
  } catch (error) {
    if (error instanceof Error && !/Failed to fetch/i.test(error.message)) {
      throw error;
    }

    const backendUrl = getApiBaseUrl() || window.location.origin;
    throw new Error(
      `Cannot reach backend at ${backendUrl}. Start the API server and try again.`,
    );
  }
}

export function getBackendUrl(): string {
  const backendUrl = import.meta.env.VITE_BACKEND_TARGET;
  if (!backendUrl || typeof backendUrl !== "string") return "";
  let formattedUrl = backendUrl.trim();
  if (formattedUrl.startsWith("http")) {
    if (formattedUrl.endsWith("/")) formattedUrl = formattedUrl.slice(0, -1);
    return formattedUrl;
  }
  return "";
}

export async function uploadMedia(file: File): Promise<UploadMediaResponse> {
  const form = new FormData();
  form.append("file", file);
  const res = await requestApi(
    "/api/upload",
    { method: "POST", body: form },
    "Upload failed",
  );
  return res.json();
}

export async function uploadVideo(file: File): Promise<string> {
  const data = await uploadMedia(file);
  return data.media_id;
}

export async function analyzeMediaFaces(
  mediaId: string,
): Promise<DetectFacesResponse> {
  const res = await requestApi(
    "/api/detect-faces",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ media_id: mediaId }),
      signal: AbortSignal.timeout(120_000),
    },
    "Detection failed",
  );
  return res.json();
}

export async function detectFaces(mediaId: string): Promise<DetectFacesResponse> {
  return analyzeMediaFaces(mediaId);
}

export async function uploadReference(
  videoId: string,
  file: File,
): Promise<void> {
  const form = new FormData();
  form.append("file", file);
  await requestApi(
    `/api/upload-reference/${videoId}`,
    {
      method: "POST",
      body: form,
    },
    "Reference upload failed",
  );
}

export async function startFaceSwapJob(
  mediaId: string,
  faceIds: string[],
  options?: {
    startFrame?: number;
    endFrame?: number;
    stylePrompt?: string;
  },
): Promise<string> {
  const res = await requestApi(
    "/api/swap",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        media_id: mediaId,
        face_ids: faceIds,
        start_frame: options?.startFrame,
        end_frame: options?.endFrame,
        style_prompt: options?.stylePrompt || null,
      }),
    },
    "Swap failed",
  );
  const data: SwapResponse = await res.json();
  return data.job_id;
}

export async function startSwap(
  mediaId: string,
  faceIds: string[],
  options?: {
    startFrame?: number;
    endFrame?: number;
    stylePrompt?: string;
  },
): Promise<string> {
  return startFaceSwapJob(mediaId, faceIds, options);
}

export async function getJobStatus(jobId: string): Promise<StatusResponse> {
  const res = await requestApi(
    `/api/status/${jobId}`,
    {},
    "Status check failed",
  );
  return res.json();
}

export async function getStatus(jobId: string): Promise<StatusResponse> {
  return getJobStatus(jobId);
}

export async function reAnalyze(jobId: string): Promise<UploadMediaResponse> {
  const res = await requestApi(
    `/api/re-analyze/${jobId}`,
    { method: "POST" },
    "Re-analysis failed",
  );
  return res.json();
}

export function getJobDownloadUrl(jobId: string): string {
  return apiUrl(`/api/download/${jobId}`);
}

export function getDownloadUrl(jobId: string): string {
  return getJobDownloadUrl(jobId);
}
