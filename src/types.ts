export interface FaceInfo {
  face_id: string;
  thumbnail: string;
  age: number;
  gender: string;
  frame_count: number;
}

export interface DetectFacesResponse {
  video_id: string;
  faces: FaceInfo[];
}

export interface SwapResponse {
  job_id: string;
}

export interface StatusResponse {
  status: "processing" | "completed" | "failed";
  progress: number;
  error: string | null;
}

export type AppStep = "upload" | "detecting" | "select" | "processing";
