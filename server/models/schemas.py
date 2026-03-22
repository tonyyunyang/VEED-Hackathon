from typing import Literal

from pydantic import BaseModel, Field, model_validator

MediaType = Literal["video", "image"]


class MediaRequestBase(BaseModel):
    media_id: str | None = None
    video_id: str | None = None

    @model_validator(mode="after")
    def _sync_media_ids(self):
        resolved_media_id = self.media_id or self.video_id
        if not resolved_media_id:
            raise ValueError("media_id or video_id is required")
        self.media_id = resolved_media_id
        self.video_id = resolved_media_id
        return self


class UploadResponse(BaseModel):
    video_id: str
    media_id: str
    media_type: MediaType


class DetectFacesRequest(MediaRequestBase):
    pass


class FaceInfo(BaseModel):
    face_id: str
    thumbnail: str
    age: int
    gender: str
    frame_count: int
    frames: dict[str, list[float]] = Field(default_factory=dict)


class DetectFacesResponse(BaseModel):
    video_id: str
    media_id: str
    media_type: MediaType
    fps: float
    total_frames: int
    width: int | None = None
    height: int | None = None
    faces: list[FaceInfo]


class SwapRequest(MediaRequestBase):
    face_ids: list[str]
    start_frame: int | None = None
    end_frame: int | None = None
    style_prompt: str | None = Field(
        default=None,
        description="Optional style description for AI-generated faces "
        "(e.g. 'wearing sunglasses', 'with face paint')",
    )


class SwapResponse(BaseModel):
    job_id: str
    media_id: str | None = None
    media_type: MediaType | None = None


class StatusResponse(BaseModel):
    status: str
    progress: float
    error: str | None = None
    warnings: list[str] | None = None
    phase: str | None = None
    message: str | None = None
    completed_frames: int | None = None
    total_frames: int | None = None
    media_id: str | None = None
    media_type: MediaType | None = None
    output_filename: str | None = None
