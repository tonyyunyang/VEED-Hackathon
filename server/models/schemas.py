from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
    video_id: str


class DetectFacesRequest(BaseModel):
    video_id: str


class FaceInfo(BaseModel):
    face_id: str
    thumbnail: str
    age: int
    gender: str
    frame_count: int
    frames: dict[str, list[float]] = Field(default_factory=dict)


class DetectFacesResponse(BaseModel):
    video_id: str
    fps: float
    faces: list[FaceInfo]


class SwapRequest(BaseModel):
    video_id: str
    face_ids: list[str]


class SwapResponse(BaseModel):
    job_id: str


class StatusResponse(BaseModel):
    status: str
    progress: float
    error: str | None = None
