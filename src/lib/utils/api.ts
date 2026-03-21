import type {
  DetectFacesResponse,
  StatusResponse,
  SwapResponse,
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

export async function uploadVideo(file: File): Promise<string> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch("/api/upload", { method: "POST", body: form });
  if (!res.ok) throw new Error(`Upload failed: ${res.statusText}`);
  const data = await res.json();
  return data.video_id;
}

export async function detectFaces(
  videoId: string
): Promise<DetectFacesResponse> {
  const res = await fetch("/api/detect-faces", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ video_id: videoId }),
    signal: AbortSignal.timeout(120_000),
  });
  if (!res.ok) throw new Error(`Detection failed: ${res.statusText}`);
  return res.json();
}

export async function startSwap(
  videoId: string,
  faceIds: string[]
): Promise<string> {
  const res = await fetch("/api/swap", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ video_id: videoId, face_ids: faceIds }),
  });
  if (!res.ok) throw new Error(`Swap failed: ${res.statusText}`);
  const data: SwapResponse = await res.json();
  return data.job_id;
}

export async function getStatus(jobId: string): Promise<StatusResponse> {
  const res = await fetch(`/api/status/${jobId}`);
  if (!res.ok) throw new Error(`Status check failed: ${res.statusText}`);
  return res.json();
}

export function getDownloadUrl(jobId: string): string {
  return `/api/download/${jobId}`;
}
