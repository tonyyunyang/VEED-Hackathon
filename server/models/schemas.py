from pydantic import BaseModel


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


class DetectFacesResponse(BaseModel):
    video_id: str
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
