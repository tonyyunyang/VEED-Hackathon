export type BoundingBox = [number, number, number, number];

export interface FaceInfo {
  face_id: string;
  thumbnail: string;
  age: number;
  gender: string;
  frame_count: number;
  frames: Record<string, BoundingBox>;
}

export interface DetectFacesResponse {
  video_id: string;
  fps: number;
  faces: FaceInfo[];
}

export interface SwapResponse {
  job_id: string;
}

export interface StatusResponse {
  status: "processing" | "completed" | "failed";
  progress: number;
  error: string | null;
  phase?: string | null;
  message?: string | null;
  completed_frames?: number | null;
  total_frames?: number | null;
}

export type AppStep =
  | "gallery"
  | "upload"
  | "detecting"
  | "select"
  | "processing"
  | "player";
