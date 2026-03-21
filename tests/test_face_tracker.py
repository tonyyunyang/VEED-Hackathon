"""Tests for server/services/face_tracker.py — face detection and clustering."""
import os
import sys
import shutil
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))

from services.video import extract_frames
from services.face_tracker import detect_and_cluster, save_faces_json, load_faces_json

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
TEST_VIDEO = os.path.join(FIXTURES, "test_video.mp4")


@pytest.fixture
def extracted_frames():
    """Extract frames from test video into a temp dir."""
    d = tempfile.mkdtemp()
    frames_dir = os.path.join(d, "frames")
    info = extract_frames(TEST_VIDEO, frames_dir)
    yield d, frames_dir, info
    shutil.rmtree(d)


def test_detect_and_cluster(extracted_frames):
    storage_dir, frames_dir, info = extracted_frames

    result = detect_and_cluster(frames_dir, storage_dir, subsample=10)

    assert "faces" in result
    # Kids party video should have at least one face
    assert len(result["faces"]) >= 1

    # Check face data structure
    for face_id, face_data in result["faces"].items():
        assert face_id.startswith("face_")
        assert "age" in face_data
        assert "gender" in face_data
        assert "thumbnail" in face_data
        assert "embedding" in face_data
        assert "frames" in face_data
        assert "frame_count" in face_data

        # Thumbnail should be a base64 data URI
        assert face_data["thumbnail"].startswith("data:image/jpeg;base64,")

        # Embedding should be 512-dim
        assert len(face_data["embedding"]) == 512

        # Frame count should match frames dict
        assert face_data["frame_count"] == len(face_data["frames"])

        # Age should be reasonable
        assert 0 < face_data["age"] < 100

        # Gender should be M or F (InsightFace convention)
        assert face_data["gender"] in (0, 1, "M", "F", "male", "female")


def test_save_and_load_faces_json(extracted_frames):
    storage_dir, frames_dir, info = extracted_frames

    faces_data = detect_and_cluster(frames_dir, storage_dir, subsample=10)
    json_path = os.path.join(storage_dir, "faces.json")

    save_faces_json(faces_data, info, json_path)

    assert os.path.exists(json_path)

    loaded = load_faces_json(json_path)
    assert "fps" in loaded
    assert "total_frames" in loaded
    assert "faces" in loaded
    assert loaded["fps"] == info["fps"]
    assert len(loaded["faces"]) == len(faces_data["faces"])
