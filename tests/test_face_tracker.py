"""Tests for server/services/face_tracker.py."""

import json
import os
import sys
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))

from services import face_tracker


def _write_frame(path: str, color: tuple[int, int, int]) -> None:
    image = np.zeros((96, 128, 3), dtype=np.uint8)
    image[:] = color
    assert cv2.imwrite(path, image)


def _make_frames(frames_dir: str, count: int = 5) -> None:
    os.makedirs(frames_dir, exist_ok=True)
    for index in range(count):
        _write_frame(
            os.path.join(frames_dir, f"frame_{index + 1:04d}.jpg"),
            (20 * index, 30 * index, 40 * index),
        )


def _make_tracker_export(json_path: str) -> dict:
    export = {
        "video_metadata": {"fps": 30.0, "width": 128, "height": 96},
        "track_summary": {
            "num_ids_total": 2,
            "ids": [
                {"id": 7, "label": "A", "first_frame": 1, "last_frame": 2},
                {"id": 3, "label": "B", "first_frame": 4, "last_frame": 4},
            ],
        },
        "frames": {
            "1": [
                {
                    "bbox": [10, 15, 30, 35],
                    "center_point": [20, 25],
                    "confidence": 0.9,
                    "id": 7,
                    "label": "A",
                }
            ],
            "2": [
                {
                    "bbox": [12, 16, 32, 36],
                    "center_point": [22, 26],
                    "confidence": 0.8,
                    "id": 7,
                    "label": "A",
                }
            ],
            "4": [
                {
                    "bbox": [40, 20, 60, 50],
                    "center_point": [50, 35],
                    "confidence": 0.95,
                    "id": 3,
                    "label": "B",
                }
            ],
        },
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(export, f)
    return export


def test_detect_and_cluster_uses_tracker_cli(monkeypatch, tmp_path):
    storage_dir = tmp_path / "storage"
    frames_dir = storage_dir / "frames"
    storage_dir.mkdir()
    _make_frames(str(frames_dir), count=5)
    (storage_dir / "original.mp4").touch()

    tracker_json_path = storage_dir / "original.tracks.json"
    _make_tracker_export(str(tracker_json_path))

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return SimpleNamespace(stdout=f"JSON: {tracker_json_path}\n")

    metadata_calls = []

    def fake_extract_face_metadata(frames_dir_arg, frame_idx, bbox, storage_dir_arg, face_id):
        metadata_calls.append((frames_dir_arg, frame_idx, bbox, storage_dir_arg, face_id))
        return {
            "age": 31,
            "gender": "female",
            "thumbnail": "data:image/jpeg;base64,TEST",
            "thumbnail_path": f"{face_id}_thumb.jpg",
            "embedding": [1.0] * 512,
        }

    monkeypatch.setattr(face_tracker, "DUMMY_TRACKING", False)
    monkeypatch.setattr(face_tracker.subprocess, "run", fake_run)
    monkeypatch.setattr(face_tracker, "_extract_face_metadata", fake_extract_face_metadata)

    result = face_tracker.detect_and_cluster(str(frames_dir), str(storage_dir), subsample=10)

    assert len(calls) == 1
    cmd = calls[0][0]
    assert cmd[0] == sys.executable
    assert cmd[1:3] == ["-m", "movie_like_shots.cli"]
    assert cmd[3] == str(storage_dir / "original.mp4")
    assert "--output-dir" in cmd
    assert str(storage_dir) in cmd

    assert list(result["faces"].keys()) == ["face_0", "face_1"]

    face_0 = result["faces"]["face_0"]
    face_1 = result["faces"]["face_1"]
    assert face_0["frame_count"] == 2
    assert face_0["frames"] == {
        "1": [10.0, 15.0, 30.0, 35.0],
        "2": [12.0, 16.0, 32.0, 36.0],
    }
    assert face_1["frame_count"] == 1
    assert face_1["frames"] == {"4": [40.0, 20.0, 60.0, 50.0]}
    assert metadata_calls[0][1] == 1
    assert metadata_calls[1][1] == 4


def test_extract_face_clips_uses_stored_bboxes(monkeypatch, tmp_path):
    frames_dir = tmp_path / "frames"
    output_dir = tmp_path / "clips"
    _make_frames(str(frames_dir), count=5)

    faces_json = {
        "faces": {
            "face_0": {
                "age": 31,
                "gender": "female",
                "thumbnail": "data:image/jpeg;base64,TEST",
                "thumbnail_path": "face_0_thumb.jpg",
                "embedding": [0.0] * 512,
                "frames": {
                    "0": [10.0, 10.0, 34.0, 34.0],
                    "2": [12.0, 11.0, 36.0, 35.0],
                    "4": [14.0, 12.0, 38.0, 36.0],
                },
                "frame_count": 3,
            }
        }
    }

    def fail_if_called():
        raise AssertionError("extract_face_clips should not re-detect faces")

    monkeypatch.setattr(face_tracker, "_get_app", fail_if_called)

    manifests = face_tracker.extract_face_clips(
        str(frames_dir),
        faces_json,
        ["face_0"],
        str(output_dir),
    )

    assert "face_0" in manifests
    manifest = manifests["face_0"]
    assert len(manifest["crops"]) == 3

    for fname, (x1, y1, x2, y2) in manifest["crops"].items():
        crop_path = os.path.join(manifest["clip_dir"], fname)
        assert os.path.exists(crop_path)
        crop = cv2.imread(crop_path)
        assert crop is not None
        assert crop.shape[0] == y2 - y1
        assert crop.shape[1] == x2 - x1


def test_dummy_mode_remains_available(monkeypatch, tmp_path):
    frames_dir = tmp_path / "frames"
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir()
    _make_frames(str(frames_dir), count=2)

    monkeypatch.setattr(face_tracker, "DUMMY_TRACKING", True)

    result = face_tracker.detect_and_cluster(str(frames_dir), str(storage_dir), subsample=1)

    assert len(result["faces"]) == 3
    for face_data in result["faces"].values():
        assert face_data["thumbnail"].startswith("data:image/jpeg;base64,")
        assert len(face_data["embedding"]) == 512
        assert face_data["frame_count"] == len(face_data["frames"])


def test_save_and_load_faces_json_round_trip(tmp_path):
    faces_data = {
        "faces": {
            "face_0": {
                "age": 31,
                "gender": "female",
                "thumbnail": "data:image/jpeg;base64,TEST",
                "thumbnail_path": "face_0_thumb.jpg",
                "embedding": [1.0] * 512,
                "frames": {"0": [1.0, 2.0, 3.0, 4.0]},
                "frame_count": 1,
            }
        }
    }
    video_info = {"fps": 30.0, "total_frames": 10}
    json_path = tmp_path / "faces.json"

    face_tracker.save_faces_json(faces_data, video_info, str(json_path))

    loaded = face_tracker.load_faces_json(str(json_path))
    assert loaded["fps"] == 30.0
    assert loaded["total_frames"] == 10
    assert loaded["faces"]["face_0"]["frame_count"] == 1
