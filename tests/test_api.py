"""Tests for server/main.py — FastAPI endpoint integration tests."""
import os
import sys
import shutil

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))

# Set up storage dir before importing app
os.environ.setdefault("ENABLE_LIPSYNC", "false")

from main import app
from config import STORAGE_DIR

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
TEST_VIDEO = os.path.join(FIXTURES, "test_video.mp4")

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_storage():
    """Clean storage dir before/after each test."""
    os.makedirs(STORAGE_DIR, exist_ok=True)
    yield
    # Don't remove storage entirely, just individual test dirs
    # to avoid interfering with other tests


def test_upload_valid_video():
    with open(TEST_VIDEO, "rb") as f:
        response = client.post(
            "/api/upload",
            files={"file": ("test.mp4", f, "video/mp4")},
        )
    assert response.status_code == 200
    data = response.json()
    assert "video_id" in data
    assert len(data["video_id"]) == 8

    # Cleanup
    video_dir = os.path.join(STORAGE_DIR, data["video_id"])
    if os.path.exists(video_dir):
        shutil.rmtree(video_dir)


def test_upload_invalid_format():
    response = client.post(
        "/api/upload",
        files={"file": ("test.txt", b"not a video", "text/plain")},
    )
    assert response.status_code == 400


def test_detect_faces_not_found():
    response = client.post(
        "/api/detect-faces",
        json={"video_id": "nonexist"},
    )
    assert response.status_code == 404


def test_status_not_found():
    response = client.get("/api/status/nonexist")
    assert response.status_code == 404


def test_download_not_found():
    response = client.get("/api/download/nonexist")
    assert response.status_code == 404


def test_upload_and_detect_faces():
    """Full integration: upload video then detect faces."""
    # Upload
    with open(TEST_VIDEO, "rb") as f:
        upload_resp = client.post(
            "/api/upload",
            files={"file": ("test.mp4", f, "video/mp4")},
        )
    assert upload_resp.status_code == 200
    video_id = upload_resp.json()["video_id"]

    # Detect faces
    detect_resp = client.post(
        "/api/detect-faces",
        json={"video_id": video_id},
    )
    assert detect_resp.status_code == 200
    data = detect_resp.json()
    assert data["video_id"] == video_id
    assert "faces" in data
    assert isinstance(data["faces"], list)

    # Should have detected at least one face in the kids party video
    assert len(data["faces"]) >= 1

    for face in data["faces"]:
        assert "face_id" in face
        assert "thumbnail" in face
        assert "age" in face
        assert "gender" in face
        assert "frame_count" in face
        assert face["frame_count"] > 0

    # Verify faces.json was written
    faces_json_path = os.path.join(STORAGE_DIR, video_id, "faces.json")
    assert os.path.exists(faces_json_path)

    # Verify frames were extracted
    frames_dir = os.path.join(STORAGE_DIR, video_id, "frames")
    assert os.path.isdir(frames_dir)
    frames = [f for f in os.listdir(frames_dir) if f.endswith(".jpg")]
    assert len(frames) > 0

    # Cleanup
    shutil.rmtree(os.path.join(STORAGE_DIR, video_id))


def test_swap_without_detect():
    """Swap should fail if detect-faces hasn't been run."""
    # Upload only
    with open(TEST_VIDEO, "rb") as f:
        upload_resp = client.post(
            "/api/upload",
            files={"file": ("test.mp4", f, "video/mp4")},
        )
    video_id = upload_resp.json()["video_id"]

    # Try swap without detecting
    swap_resp = client.post(
        "/api/swap",
        json={"video_id": video_id, "face_ids": ["face_0"]},
    )
    assert swap_resp.status_code == 400

    # Cleanup
    shutil.rmtree(os.path.join(STORAGE_DIR, video_id))
