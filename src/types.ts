export type BoundingBox = [number, number, number, number];
export type MediaType = "video" | "image";

export interface UploadMediaResponse {
  video_id: string;
  media_id: string;
  media_type: MediaType;
}

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
  media_id: string;
  media_type: MediaType;
  fps: number;
  total_frames: number;
  width?: number | null;
  height?: number | null;
  faces: FaceInfo[];
}

export interface SwapResponse {
  job_id: string;
  media_id?: string | null;
  media_type?: MediaType | null;
}

export interface StatusResponse {
  status: "processing" | "completed" | "failed";
  progress: number;
  error: string | null;
  warnings?: string[] | null;
  phase?: string | null;
  message?: string | null;
  completed_frames?: number | null;
  total_frames?: number | null;
  media_id?: string | null;
  media_type?: MediaType | null;
  output_filename?: string | null;
}

export type AppStep =
  | "gallery"
  | "upload"
  | "detecting"
  | "select"
  | "processing"
  | "player";
