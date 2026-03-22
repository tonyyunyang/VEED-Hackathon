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
        return {
            "fps": 24.0,
            "total_frames": 1,
            "width": 1280,
            "height": 720,
            "media_type": "video",
        }

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


def _mock_image_stack(monkeypatch):
    def fake_stage_image(image_path, output_dir):
        os.makedirs(output_dir, exist_ok=True)
        with open(os.path.join(output_dir, "frame_0001.jpg"), "wb") as f:
            f.write(b"fake-image-frame")
        return {
            "fps": 1.0,
            "total_frames": 1,
            "width": 640,
            "height": 480,
            "media_type": "image",
            "output_extension": ".png",
        }

    def fake_detect_faces_in_image(image_path, storage_dir):
        return {
            "faces": {
                "face_0": {
                    "thumbnail": "data:image/jpeg;base64,ZmFrZQ==",
                    "age": 28,
                    "gender": "female",
                    "frame_count": 1,
                    "frames": {"0": [5.0, 6.0, 25.0, 26.0]},
                }
            }
        }

    def fail_if_audio_called(*args, **kwargs):
        raise AssertionError("extract_audio should not run for images")

    monkeypatch.setattr(main.video, "stage_image_as_frames", fake_stage_image)
    monkeypatch.setattr(main.face_tracker, "detect_faces_in_image", fake_detect_faces_in_image)
    monkeypatch.setattr(main.video, "extract_audio", fail_if_audio_called)


def test_upload_valid_video():
    response = client.post(
        "/api/upload",
        files={"file": ("test.mp4", BytesIO(b"fake video"), "video/mp4")},
    )
    assert response.status_code == 200
    data = response.json()
    assert "video_id" in data
    assert "media_id" in data
    assert data["media_type"] == "video"
    assert len(data["video_id"]) == 8


def test_upload_valid_image():
    response = client.post(
        "/api/upload",
        files={"file": ("portrait.png", BytesIO(b"fake image"), "image/png")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["media_type"] == "image"
    assert data["media_id"] == data["video_id"]


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
        json={"media_id": video_id},
    )
    assert detect_resp.status_code == 200

    data = detect_resp.json()
    assert data["video_id"] == video_id
    assert data["media_id"] == video_id
    assert data["media_type"] == "video"
    assert data["fps"] == 24.0
    assert data["total_frames"] == 1
    assert data["width"] == 1280
    assert data["height"] == 720
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


def test_upload_and_detect_faces_for_image(monkeypatch, isolated_storage):
    _mock_image_stack(monkeypatch)

    upload_resp = client.post(
        "/api/upload",
        files={"file": ("portrait.png", BytesIO(b"fake image"), "image/png")},
    )
    assert upload_resp.status_code == 200
    media_id = upload_resp.json()["media_id"]

    detect_resp = client.post(
        "/api/detect-faces",
        json={"media_id": media_id},
    )
    assert detect_resp.status_code == 200

    data = detect_resp.json()
    assert data["video_id"] == media_id
    assert data["media_id"] == media_id
    assert data["media_type"] == "image"
    assert data["fps"] == 1.0
    assert data["total_frames"] == 1
    assert data["width"] == 640
    assert data["height"] == 480
    assert len(data["faces"]) == 1
    assert data["faces"][0]["frames"] == {"0": [5.0, 6.0, 25.0, 26.0]}

    faces_json_path = os.path.join(main.STORAGE_DIR, media_id, "faces.json")
    assert os.path.exists(faces_json_path)


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


def test_swap_rejects_frame_trim_for_image(isolated_storage):
    response = client.post(
        "/api/upload",
        files={"file": ("portrait.png", BytesIO(b"fake image"), "image/png")},
    )
    media_id = response.json()["media_id"]
    media_dir = os.path.join(main.STORAGE_DIR, media_id)
    with open(os.path.join(media_dir, "faces.json"), "w", encoding="utf-8") as f:
        f.write(
            '{"fps": 1.0, "total_frames": 1, "media_type": "image", "faces": {"face_0": {"thumbnail": "", "age": 0, "gender": "unknown", "frame_count": 1, "frames": {"0": [0.0, 0.0, 1.0, 1.0]}}}}'
        )

    swap_resp = client.post(
        "/api/swap",
        json={
            "media_id": media_id,
            "face_ids": ["face_0"],
            "start_frame": 0,
            "end_frame": 1,
        },
    )
    assert swap_resp.status_code == 400


def test_status_response_includes_progress_metadata():
    main.jobs["job123"] = {
        "status": "processing",
        "progress": 0.42,
        "error": None,
        "video_id": "video123",
        "media_id": "video123",
        "media_type": "video",
        "phase": "swapping",
        "message": "Swapping face_0 (1/2)",
        "completed_frames": 12,
        "total_frames": 48,
        "output_filename": None,
    }

    response = client.get("/api/status/job123")

    assert response.status_code == 200
    assert response.json() == {
        "status": "processing",
        "progress": 0.42,
        "error": None,
        "phase": "swapping",
        "message": "Swapping face_0 (1/2)",
        "completed_frames": 12,
        "total_frames": 48,
        "media_id": "video123",
        "media_type": "video",
        "output_filename": None,
    }


def test_download_completed_image(isolated_storage):
    media_dir = os.path.join(main.STORAGE_DIR, "img123")
    os.makedirs(media_dir, exist_ok=True)
    output_path = os.path.join(media_dir, "output.png")
    with open(output_path, "wb") as f:
        f.write(b"fake-png")

    main.jobs["job-img"] = {
        "status": "completed",
        "progress": 1.0,
        "error": None,
        "video_id": "img123",
        "media_id": "img123",
        "media_type": "image",
        "phase": "completed",
        "message": "Swap complete",
        "completed_frames": 1,
        "total_frames": 1,
        "output_filename": "swapped.png",
        "output_path": output_path,
        "output_media_type": "image/png",
    }

    response = client.get("/api/download/job-img")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/png")
    assert "swapped.png" in response.headers.get("content-disposition", "")
