import type {
  DetectFacesResponse,
  StatusResponse,
  SwapResponse,
  UploadMediaResponse,
} from "../../types";

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
  const res = await fetch("/api/upload", { method: "POST", body: form });
  if (!res.ok) throw new Error(`Upload failed: ${res.statusText}`);
  return res.json();
}

export async function uploadVideo(file: File): Promise<string> {
  const data = await uploadMedia(file);
  return data.media_id;
}

export async function analyzeMediaFaces(
  mediaId: string
): Promise<DetectFacesResponse> {
  const res = await fetch("/api/detect-faces", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ media_id: mediaId }),
    signal: AbortSignal.timeout(120_000),
  });
  if (!res.ok) throw new Error(`Detection failed: ${res.statusText}`);
  return res.json();
}

export async function detectFaces(
  mediaId: string
): Promise<DetectFacesResponse> {
  return analyzeMediaFaces(mediaId);
}

export async function startFaceSwapJob(
  mediaId: string,
  faceIds: string[],
  options?: {
    startFrame?: number;
    endFrame?: number;
  },
): Promise<string> {
  const res = await fetch("/api/swap", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      media_id: mediaId,
      face_ids: faceIds,
      start_frame: options?.startFrame,
      end_frame: options?.endFrame,
    }),
  });
  if (!res.ok) throw new Error(`Swap failed: ${res.statusText}`);
  const data: SwapResponse = await res.json();
  return data.job_id;
}

export async function startSwap(
  mediaId: string,
  faceIds: string[],
  options?: {
    startFrame?: number;
    endFrame?: number;
  },
): Promise<string> {
  return startFaceSwapJob(mediaId, faceIds, options);
}

export async function getJobStatus(jobId: string): Promise<StatusResponse> {
  const res = await fetch(`/api/status/${jobId}`);
  if (!res.ok) throw new Error(`Status check failed: ${res.statusText}`);
  return res.json();
}

export async function getStatus(jobId: string): Promise<StatusResponse> {
  return getJobStatus(jobId);
}

export function getJobDownloadUrl(jobId: string): string {
  return `/api/download/${jobId}`;
}

export function getDownloadUrl(jobId: string): string {
  return getJobDownloadUrl(jobId);
}
