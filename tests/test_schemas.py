"""Tests for server/models/schemas.py — Pydantic model validation."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))

from models.schemas import (
    UploadResponse, DetectFacesRequest, DetectFacesResponse,
    FaceInfo, SwapRequest, SwapResponse, StatusResponse,
)


def test_upload_response():
    r = UploadResponse(video_id="abc123", media_id="abc123", media_type="video")
    assert r.video_id == "abc123"
    assert r.media_id == "abc123"
    assert r.media_type == "video"


def test_detect_faces_request_accepts_video_id():
    r = DetectFacesRequest(video_id="abc123")
    assert r.video_id == "abc123"
    assert r.media_id == "abc123"


def test_detect_faces_request_accepts_media_id():
    r = DetectFacesRequest(media_id="media123")
    assert r.video_id == "media123"
    assert r.media_id == "media123"


def test_face_info():
    f = FaceInfo(
        face_id="face_0",
        thumbnail="data:image/jpeg;base64,abc",
        age=25,
        gender="male",
        frame_count=10,
        frames={"0": [1.0, 2.0, 3.0, 4.0]},
    )
    assert f.face_id == "face_0"
    assert f.age == 25
    assert f.frames["0"] == [1.0, 2.0, 3.0, 4.0]


def test_detect_faces_response():
    r = DetectFacesResponse(
        video_id="abc",
        media_id="abc",
        media_type="image",
        fps=24.0,
        total_frames=1,
        width=640,
        height=480,
        faces=[
            FaceInfo(
                face_id="face_0",
                thumbnail="thumb",
                age=30,
                gender="female",
                frame_count=5,
            )
        ],
    )
    assert len(r.faces) == 1
    assert r.fps == 24.0
    assert r.media_type == "image"
    assert r.total_frames == 1
    assert r.faces[0].gender == "female"


def test_swap_request_accepts_video_id():
    r = SwapRequest(video_id="abc", face_ids=["face_0", "face_1"])
    assert r.media_id == "abc"
    assert len(r.face_ids) == 2


def test_swap_request_accepts_media_id():
    r = SwapRequest(media_id="asset_1", face_ids=["face_0"])
    assert r.video_id == "asset_1"
    assert r.media_id == "asset_1"


def test_swap_response():
    r = SwapResponse(job_id="job_123", media_id="abc", media_type="image")
    assert r.job_id == "job_123"
    assert r.media_type == "image"


def test_status_response_processing():
    r = StatusResponse(
        status="processing",
        progress=0.5,
        media_type="video",
        warnings=["Runware fallback in use"],
    )
    assert r.error is None
    assert r.progress == 0.5
    assert r.media_type == "video"
    assert r.warnings == ["Runware fallback in use"]


def test_status_response_failed():
    r = StatusResponse(
        status="failed",
        progress=0.0,
        error="Something broke",
        warnings=None,
        output_filename="swapped.png",
    )
    assert r.error == "Something broke"
    assert r.output_filename == "swapped.png"
