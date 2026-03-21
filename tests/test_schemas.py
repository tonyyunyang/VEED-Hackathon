"""Tests for server/models/schemas.py — Pydantic model validation."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))

from models.schemas import (
    UploadResponse, DetectFacesRequest, DetectFacesResponse,
    FaceInfo, SwapRequest, SwapResponse, StatusResponse,
)


def test_upload_response():
    r = UploadResponse(video_id="abc123")
    assert r.video_id == "abc123"


def test_detect_faces_request():
    r = DetectFacesRequest(video_id="abc123")
    assert r.video_id == "abc123"


def test_face_info():
    f = FaceInfo(
        face_id="face_0",
        thumbnail="data:image/jpeg;base64,abc",
        age=25,
        gender="male",
        frame_count=10,
    )
    assert f.face_id == "face_0"
    assert f.age == 25


def test_detect_faces_response():
    r = DetectFacesResponse(
        video_id="abc",
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
    assert r.faces[0].gender == "female"


def test_swap_request():
    r = SwapRequest(video_id="abc", face_ids=["face_0", "face_1"])
    assert len(r.face_ids) == 2


def test_swap_response():
    r = SwapResponse(job_id="job_123")
    assert r.job_id == "job_123"


def test_status_response_processing():
    r = StatusResponse(status="processing", progress=0.5)
    assert r.error is None
    assert r.progress == 0.5


def test_status_response_failed():
    r = StatusResponse(status="failed", progress=0.0, error="Something broke")
    assert r.error == "Something broke"
