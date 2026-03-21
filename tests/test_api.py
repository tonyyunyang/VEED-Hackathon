"""Tests for server/main.py — FastAPI endpoint integration tests."""

import os
import sys
from io import BytesIO

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))

os.environ.setdefault("ENABLE_LIPSYNC", "false")
os.environ.setdefault("TRACKER_BACKEND", "movie_like_shots")
os.environ.setdefault("TRACKER_TYPE", "ocsort")
os.environ.setdefault("TRACKER_DEVICE", "cpu")
os.environ.setdefault("DUMMY_TRACKING", "false")

import main

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    """Route all server writes into a test-local storage directory."""

    storage_dir = tmp_path / "storage"
    storage_dir.mkdir()
    monkeypatch.setattr(main, "STORAGE_DIR", str(storage_dir))
    main.jobs.clear()
    yield storage_dir
    main.jobs.clear()


def _mock_tracker_stack(monkeypatch):
    def fake_extract_frames(video_path, output_dir):
        os.makedirs(output_dir, exist_ok=True)
        with open(os.path.join(output_dir, "frame_0001.jpg"), "wb") as f:
            f.write(b"fake-frame")
        return {"fps": 24.0, "total_frames": 1}

    def fake_extract_audio(video_path, audio_path):
        with open(audio_path, "wb") as f:
            f.write(b"")
        return True

    def fake_detect_and_cluster(frames_dir, storage_dir, subsample):
        return {
            "faces": {
                "face_0": {
                    "thumbnail": "data:image/jpeg;base64,ZmFrZQ==",
                    "age": 34,
                    "gender": "male",
                    "frame_count": 1,
                    "frames": {"0": [10.0, 10.0, 20.0, 20.0]},
                }
            }
        }

    monkeypatch.setattr(main.video, "extract_frames", fake_extract_frames)
    monkeypatch.setattr(main.video, "extract_audio", fake_extract_audio)
    monkeypatch.setattr(main.face_tracker, "detect_and_cluster", fake_detect_and_cluster)


def test_upload_valid_video():
    response = client.post(
        "/api/upload",
        files={"file": ("test.mp4", BytesIO(b"fake video"), "video/mp4")},
    )
    assert response.status_code == 200
    data = response.json()
    assert "video_id" in data
    assert len(data["video_id"]) == 8


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


def test_upload_and_detect_faces(monkeypatch, isolated_storage):
    """Upload a video, then detect faces through the mocked tracker stack."""

    _mock_tracker_stack(monkeypatch)

    upload_resp = client.post(
        "/api/upload",
        files={"file": ("test.mp4", BytesIO(b"fake video"), "video/mp4")},
    )
    assert upload_resp.status_code == 200
    video_id = upload_resp.json()["video_id"]

    detect_resp = client.post(
        "/api/detect-faces",
        json={"video_id": video_id},
    )
    assert detect_resp.status_code == 200

    data = detect_resp.json()
    assert data["video_id"] == video_id
    assert data["fps"] == 24.0
    assert isinstance(data["faces"], list)
    assert len(data["faces"]) == 1

    face = data["faces"][0]
    assert face["face_id"] == "face_0"
    assert face["thumbnail"].startswith("data:image/jpeg;base64,")
    assert face["age"] == 34
    assert face["gender"] == "male"
    assert face["frame_count"] == 1
    assert face["frames"] == {"0": [10.0, 10.0, 20.0, 20.0]}

    faces_json_path = os.path.join(main.STORAGE_DIR, video_id, "faces.json")
    assert os.path.exists(faces_json_path)

    frames_dir = os.path.join(main.STORAGE_DIR, video_id, "frames")
    assert os.path.isdir(frames_dir)


def test_swap_without_detect():
    """Swap should fail if detect-faces hasn't been run."""

    response = client.post(
        "/api/upload",
        files={"file": ("test.mp4", BytesIO(b"fake video"), "video/mp4")},
    )
    video_id = response.json()["video_id"]

    swap_resp = client.post(
        "/api/swap",
        json={"video_id": video_id, "face_ids": ["face_0"]},
    )
    assert swap_resp.status_code == 400
