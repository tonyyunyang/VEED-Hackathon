from __future__ import annotations

import base64
import json
import os
import random
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from config import DUMMY_TRACKING, ENABLE_FACE_METADATA_ENRICHMENT

REPO_ROOT = Path(__file__).resolve().parents[2]
TRACKER_SRC_DIR = REPO_ROOT / "face-detect-track" / "src"
TRACKER_CLI_MODULE = "movie_like_shots.cli"
DEFAULT_TRACKER_TYPE = "ocsort"
DEFAULT_TRACKER_DEVICE = "cpu"
TRACKER_DET_SIZE = 640
TRACKER_DET_THRESH = 0.35
TRACKER_NMS_THRESH = 0.4
TRACKER_NUM_BINS = 64
TRACKER_SHOT_CHANGE_THRESHOLD = 0.4
TRACKER_FILTER_TRACKS = False
TRACKER_MIN_TRACK_LENGTH = 10
TRACKER_MIN_TRACK_MEDIAN_AREA = 2500.0
TRACKER_FILTER_CONFIDENCE = False
TRACKER_MIN_CONFIDENCE = 0.5
TRACKER_USE_SHOT_CHANGE = True
TRACKER_USE_SHARED_MEMORY = True
TRACKER_TIMEOUT_SECONDS = 600
DEFAULT_TRACKER_SIMILARITY_THRESHOLD = 0.4
FACE_ANALYSIS_DEVICE = "auto"
FACE_ANALYSIS_DET_SIZE = 640

_app = None


@lru_cache(maxsize=1)
def _available_onnx_providers() -> tuple[str, ...]:
    try:
        import onnxruntime as ort
    except Exception:
        return ("CPUExecutionProvider",)
    return tuple(ort.get_available_providers())


def _resolve_face_analysis_execution(device: str, detector_size: int) -> tuple[list[str], int]:
    available = set(_available_onnx_providers())

    if device == "cpu":
        return ["CPUExecutionProvider"], -1
    if device == "cuda":
        if "CUDAExecutionProvider" in available:
            return ["CUDAExecutionProvider", "CPUExecutionProvider"], 0
        return ["CPUExecutionProvider"], -1

    if (
        sys.platform == "darwin"
        and detector_size == 640
        and "CoreMLExecutionProvider" in available
    ):
        return ["CoreMLExecutionProvider", "CPUExecutionProvider"], 0
    if "CUDAExecutionProvider" in available:
        return ["CUDAExecutionProvider", "CPUExecutionProvider"], 0
    return ["CPUExecutionProvider"], -1


def _get_app():
    global _app
    if _app is None:
        from insightface.app import FaceAnalysis

        providers, ctx_id = _resolve_face_analysis_execution(
            FACE_ANALYSIS_DEVICE,
            FACE_ANALYSIS_DET_SIZE,
        )
        _app = FaceAnalysis(name="buffalo_l", providers=providers)
        _app.prepare(
            ctx_id=ctx_id,
            det_size=(FACE_ANALYSIS_DET_SIZE, FACE_ANALYSIS_DET_SIZE),
        )
    return _app


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))


def _frame_files(frames_dir: str) -> list[str]:
    return sorted(
        f for f in os.listdir(frames_dir) if f.startswith("frame_") and f.endswith(".jpg")
    )


def _frame_area(bbox: list[float]) -> float:
    return max(0.0, float(bbox[2]) - float(bbox[0])) * max(
        0.0, float(bbox[3]) - float(bbox[1])
    )


def _normalize_gender(value: Any) -> str:
    if isinstance(value, (int, np.integer)):
        return "male" if int(value) == 1 else "female"
    gender = str(value).strip().lower()
    if gender in {"m", "male", "man", "1"}:
        return "male"
    if gender in {"f", "female", "woman", "0"}:
        return "female"
    return gender or "unknown"


def _expand_bbox(bbox: list[float], frame: np.ndarray, padding: float = 0.15) -> list[int]:
    x1, y1, x2, y2 = [float(v) for v in bbox]
    width = max(1.0, x2 - x1)
    height = max(1.0, y2 - y1)
    pad_x = width * padding
    pad_y = height * padding
    h, w = frame.shape[:2]
    left = max(0, int(np.floor(x1 - pad_x)))
    top = max(0, int(np.floor(y1 - pad_y)))
    right = min(w, int(np.ceil(x2 + pad_x)))
    bottom = min(h, int(np.ceil(y2 + pad_y)))
    if right <= left:
        right = min(w, left + 1)
    if bottom <= top:
        bottom = min(h, top + 1)
    return [left, top, right, bottom]


def _crop_face_thumbnail(frame: np.ndarray, bbox: list[float], size: int = 112) -> str:
    x1, y1, x2, y2 = [int(v) for v in bbox]
    h, w = frame.shape[:2]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        return ""
    crop = cv2.resize(crop, (size, size))
    _, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
    b64 = base64.b64encode(buf).decode()
    return f"data:image/jpeg;base64,{b64}"


def _tracker_env() -> dict[str, str]:
    env = os.environ.copy()
    pythonpath_parts = [str(TRACKER_SRC_DIR)]
    existing_pythonpath = env.get("PYTHONPATH")
    if existing_pythonpath:
        pythonpath_parts.append(existing_pythonpath)
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
    return env


def _find_original_video_path(storage_dir: str) -> str:
    storage_path = Path(storage_dir)
    for candidate in sorted(storage_path.iterdir()):
        if candidate.is_file() and candidate.name.startswith("original"):
            return str(candidate)

    for ext in (".mp4", ".mov", ".webm", ".avi"):
        candidates = sorted(storage_path.glob(f"*{ext}"))
        if candidates:
            return str(candidates[0])

    raise FileNotFoundError(f"No source video found in {storage_dir}")


def _build_tracker_command(video_path: str, output_dir: str) -> list[str]:
    command = [
        sys.executable,
        "-m",
        TRACKER_CLI_MODULE,
        video_path,
        "--output-dir",
        output_dir,
        "--tracker",
        DEFAULT_TRACKER_TYPE,
        "--device",
        DEFAULT_TRACKER_DEVICE,
    ]
    command.extend(
        [
            "--det-size",
            str(TRACKER_DET_SIZE),
            "--det-thresh",
            str(TRACKER_DET_THRESH),
            "--nms-thresh",
            str(TRACKER_NMS_THRESH),
            "--num-bins",
            str(TRACKER_NUM_BINS),
            "--shot-change-threshold",
            str(TRACKER_SHOT_CHANGE_THRESHOLD),
        ]
    )
    if not TRACKER_USE_SHOT_CHANGE:
        command.append("--disable-shot-change")
    if not TRACKER_USE_SHARED_MEMORY:
        command.append("--disable-shared-memory")
    if TRACKER_FILTER_TRACKS:
        command.append("--filter-tracks")
        command.extend(
            [
                "--min-track-length",
                str(TRACKER_MIN_TRACK_LENGTH),
                "--min-track-median-area",
                str(TRACKER_MIN_TRACK_MEDIAN_AREA),
            ]
        )
    if TRACKER_FILTER_CONFIDENCE:
        command.append("--filter-confidence")
        command.extend(["--min-confidence", str(TRACKER_MIN_CONFIDENCE)])
    return command


def _parse_tracker_json_path(stdout: str | None, default_path: str) -> str:
    if stdout:
        for line in stdout.splitlines():
            line = line.strip()
            if line.startswith("JSON:"):
                candidate = line.split("JSON:", 1)[1].strip()
                if candidate:
                    return candidate
    return default_path


def _run_tracker_pipeline(video_path: str, output_dir: str) -> str:
    command = _build_tracker_command(video_path, output_dir)
    try:
        completed = subprocess.run(
            command,
            cwd=str(REPO_ROOT),
            env=_tracker_env(),
            capture_output=True,
            text=True,
            check=True,
            timeout=TRACKER_TIMEOUT_SECONDS,
        )
    except subprocess.CalledProcessError as exc:
        details = exc.stderr or exc.stdout or str(exc)
        raise RuntimeError(
            f"movie_like_shots tracker failed for {video_path}: {details}"
        ) from exc

    default_json_path = os.path.join(
        output_dir, f"{Path(video_path).stem}.tracks.json"
    )
    json_path = _parse_tracker_json_path(getattr(completed, "stdout", None), default_json_path)
    if not os.path.exists(json_path):
        raise FileNotFoundError(
            f"Tracker JSON not found at {json_path}. stdout={getattr(completed, 'stdout', '')!r}"
        )
    return json_path


def _load_tracker_export(json_path: str) -> dict[str, Any]:
    with open(json_path, encoding="utf-8") as f:
        return json.load(f)


def _collect_track_entries(tracker_export: dict[str, Any]) -> dict[int, list[dict[str, Any]]]:
    track_entries: dict[int, list[dict[str, Any]]] = {}
    for frame_key, frame_entries in tracker_export.get("frames", {}).items():
        frame_index = int(frame_key)
        for entry in frame_entries:
            track_id = int(entry["id"])
            track_entries.setdefault(track_id, []).append(
                {
                    "frame_index": frame_index,
                    "bbox": [float(v) for v in entry["bbox"]],
                    "confidence": float(entry.get("confidence", 1.0)),
                }
            )
    return track_entries


def _ordered_track_ids(tracker_export: dict[str, Any]) -> list[int]:
    track_summary = tracker_export.get("track_summary", {})
    summary_ids = track_summary.get("ids", [])
    if summary_ids:
        summary_entries = [
            (int(entry["id"]), int(entry.get("first_frame", 0)))
            for entry in summary_ids
        ]
        return [track_id for track_id, _first_frame in sorted(
            summary_entries, key=lambda item: (item[1], item[0])
        )]

    track_entries = _collect_track_entries(tracker_export)
    return sorted(
        track_entries.keys(),
        key=lambda track_id: (
            min(entry["frame_index"] for entry in track_entries[track_id]),
            track_id,
        ),
    )


def _extract_face_metadata(
    frames_dir: str,
    representative_frame_index: int,
    representative_bbox: list[float],
    storage_dir: str,
    face_id: str,
) -> dict[str, Any]:
    frame_files = _frame_files(frames_dir)
    if representative_frame_index < 0 or representative_frame_index >= len(frame_files):
        return {
            "age": 0,
            "gender": "unknown",
            "thumbnail": "",
            "thumbnail_path": f"{face_id}_thumb.jpg",
            "embedding": [0.0] * 512,
        }

    frame_path = os.path.join(frames_dir, frame_files[representative_frame_index])
    frame = cv2.imread(frame_path)
    if frame is None:
        return {
            "age": 0,
            "gender": "unknown",
            "thumbnail": "",
            "thumbnail_path": f"{face_id}_thumb.jpg",
            "embedding": [0.0] * 512,
        }

    padded_bbox = _expand_bbox(representative_bbox, frame)
    x1, y1, x2, y2 = padded_bbox
    crop = frame[y1:y2, x1:x2]
    thumbnail = _crop_face_thumbnail(frame, padded_bbox)
    thumb_path = f"{face_id}_thumb.jpg"
    if crop.size > 0:
        cv2.imwrite(os.path.join(storage_dir, thumb_path), crop)

    age = 0
    gender = "unknown"
    embedding: list[float] = [0.0] * 512

    if crop.size > 0 and not DUMMY_TRACKING and ENABLE_FACE_METADATA_ENRICHMENT:
        faces = _get_app().get(crop)
        if faces:
            representative_face = max(
                faces,
                key=lambda face: (face.bbox[2] - face.bbox[0]) * (face.bbox[3] - face.bbox[1]),
            )
            age = int(getattr(representative_face, "age", 0) or 0)
            gender = _normalize_gender(getattr(representative_face, "gender", "unknown"))
            embedding = (
                representative_face.normed_embedding.tolist()
                if hasattr(representative_face, "normed_embedding")
                else [0.0] * 512
            )

    return {
        "age": age,
        "gender": gender,
        "thumbnail": thumbnail,
        "thumbnail_path": thumb_path,
        "embedding": embedding,
    }


def _translate_tracker_export_to_faces(
    tracker_export: dict[str, Any],
    frames_dir: str,
    storage_dir: str,
) -> dict[str, dict[str, Any]]:
    track_entries = _collect_track_entries(tracker_export)
    faces_data: dict[str, dict[str, Any]] = {}

    for face_index, track_id in enumerate(_ordered_track_ids(tracker_export)):
        entries = sorted(track_entries.get(track_id, []), key=lambda item: item["frame_index"])
        if not entries:
            continue

        representative_entry = max(entries, key=lambda item: _frame_area(item["bbox"]))
        face_id = f"face_{face_index}"
        metadata = _extract_face_metadata(
            frames_dir,
            int(representative_entry["frame_index"]),
            list(representative_entry["bbox"]),
            storage_dir,
            face_id,
        )

        faces_data[face_id] = {
            "age": metadata["age"],
            "gender": metadata["gender"],
            "thumbnail": metadata["thumbnail"],
            "thumbnail_path": metadata["thumbnail_path"],
            "embedding": metadata["embedding"],
            "frames": {
                str(entry["frame_index"]): {
                    "bbox": list(entry["bbox"]),
                    "det_score": float(entry["confidence"]),
                }
                for entry in entries
            },
            "frame_count": len(entries),
        }

    return faces_data


def _dummy_detect_and_cluster(
    frames_dir: str, storage_dir: str, subsample: int = 5
) -> dict:
    """Return 3 random square bounding boxes as fake faces for frontend dev."""
    frame_files = _frame_files(frames_dir)
    if not frame_files:
        return {"faces": {}}

    sample = cv2.imread(os.path.join(frames_dir, frame_files[0]))
    if sample is None:
        return {"faces": {}}
    h, w = sample.shape[:2]

    rng = random.Random(42)
    face_size = max(1, min(h, w) // 5)

    faces_data = {}
    for idx in range(3):
        face_id = f"face_{idx}"
        x1 = rng.randint(0, max(0, w - face_size))
        y1 = rng.randint(0, max(0, h - face_size))
        x2 = x1 + face_size
        y2 = y1 + face_size
        bbox = [float(x1), float(y1), float(x2), float(y2)]

        frames_dict = {}
        for i, _fname in enumerate(frame_files):
            if i % subsample != 0:
                continue
            frames_dict[str(i)] = {"bbox": bbox, "det_score": 1.0}

        thumbnail = _crop_face_thumbnail(sample, bbox)
        thumb_path = f"{face_id}_thumb.jpg"
        crop = sample[y1:y2, x1:x2]
        if crop.size > 0:
            cv2.imwrite(os.path.join(storage_dir, thumb_path), crop)

        faces_data[face_id] = {
            "age": rng.randint(20, 45),
            "gender": rng.choice(["male", "female"]),
            "thumbnail": thumbnail,
            "thumbnail_path": thumb_path,
            "embedding": [0.0] * 512,
            "frames": frames_dict,
            "frame_count": len(frames_dict),
        }

    return {"faces": faces_data}


def _dummy_detect_faces_in_image(image_path: str, storage_dir: str) -> dict:
    frame = cv2.imread(image_path)
    if frame is None:
        return {"faces": {}}

    h, w = frame.shape[:2]
    rng = random.Random(42)
    max_faces = 3
    face_size = max(1, min(h, w) // 4)
    faces_data = {}

    for idx in range(max_faces):
        face_id = f"face_{idx}"
        x1 = rng.randint(0, max(0, w - face_size))
        y1 = rng.randint(0, max(0, h - face_size))
        x2 = x1 + face_size
        y2 = y1 + face_size
        bbox = [float(x1), float(y1), float(x2), float(y2)]

        padded_bbox = _expand_bbox(bbox, frame)
        thumbnail = _crop_face_thumbnail(frame, padded_bbox)
        thumb_path = f"{face_id}_thumb.jpg"
        px1, py1, px2, py2 = padded_bbox
        crop = frame[py1:py2, px1:px2]
        if crop.size > 0:
            cv2.imwrite(os.path.join(storage_dir, thumb_path), crop)

        faces_data[face_id] = {
            "age": rng.randint(20, 45),
            "gender": rng.choice(["male", "female"]),
            "thumbnail": thumbnail,
            "thumbnail_path": thumb_path,
            "embedding": [0.0] * 512,
            "frames": {"0": {"bbox": bbox, "det_score": 1.0}},
            "frame_count": 1,
        }

    return {"faces": faces_data}


def detect_and_cluster(
    frames_dir: str, storage_dir: str, subsample: int = 5
) -> dict:
    if DUMMY_TRACKING:
        return _dummy_detect_and_cluster(frames_dir, storage_dir, subsample)

    video_path = _find_original_video_path(storage_dir)
    tracker_json_path = _run_tracker_pipeline(video_path, storage_dir)
    tracker_export = _load_tracker_export(tracker_json_path)
    faces_data = _translate_tracker_export_to_faces(tracker_export, frames_dir, storage_dir)
    return {"faces": faces_data}


def detect_faces_in_image(image_path: str, storage_dir: str) -> dict:
    if DUMMY_TRACKING:
        return _dummy_detect_faces_in_image(image_path, storage_dir)

    frame = cv2.imread(image_path)
    if frame is None:
        raise RuntimeError(f"Unable to read image: {image_path}")

    detected_faces = _get_app().get(frame)
    ordered_faces = sorted(
        detected_faces,
        key=lambda face: (
            round(float(face.bbox[0]), 4),
            round(float(face.bbox[1]), 4),
            -_frame_area(face.bbox.tolist()),
        ),
    )

    faces_data: dict[str, dict[str, Any]] = {}
    for face_index, detected_face in enumerate(ordered_faces):
        face_id = f"face_{face_index}"
        bbox = [float(v) for v in detected_face.bbox.tolist()]
        padded_bbox = _expand_bbox(bbox, frame)
        px1, py1, px2, py2 = padded_bbox
        crop = frame[py1:py2, px1:px2]
        thumb_path = f"{face_id}_thumb.jpg"
        if crop.size > 0:
            cv2.imwrite(os.path.join(storage_dir, thumb_path), crop)

        faces_data[face_id] = {
            "age": int(getattr(detected_face, "age", 0) or 0),
            "gender": _normalize_gender(getattr(detected_face, "gender", "unknown")),
            "thumbnail": _crop_face_thumbnail(frame, padded_bbox),
            "thumbnail_path": thumb_path,
            "embedding": (
                detected_face.normed_embedding.tolist()
                if hasattr(detected_face, "normed_embedding")
                else [0.0] * 512
            ),
            "frames": {"0": {"bbox": bbox, "det_score": float(detected_face.det_score)}},
            "frame_count": 1,
        }

    return {"faces": faces_data}


def extract_face_clips(
    frames_dir: str,
    faces_json: dict,
    selected_face_ids: list[str],
    output_base_dir: str,
    start_frame: int | None = None,
    end_frame: int | None = None,
) -> dict[str, dict]:
    """Extract per-face cropped frame sequences from full frames.

    Uses the stored per-frame tracked bboxes from faces.json, without
    re-running face detection.
    """
    frame_files = _frame_files(frames_dir)
    manifests = {}

    for face_id in selected_face_ids:
        face_data = faces_json.get("faces", {}).get(face_id)
        if not face_data:
            continue

        stored_frames = sorted(
            (
                int(frame_key),
                [float(v) for v in frame_entry["bbox"]],
            )
            for frame_key, frame_entry in face_data.get("frames", {}).items()
        )
        if start_frame is not None:
            stored_frames = [
                (frame_idx, bbox)
                for frame_idx, bbox in stored_frames
                if frame_idx >= start_frame
            ]
        if end_frame is not None:
            stored_frames = [
                (frame_idx, bbox)
                for frame_idx, bbox in stored_frames
                if frame_idx < end_frame
            ]
        if not stored_frames:
            continue

        clip_dir = os.path.join(output_base_dir, face_id)
        if os.path.exists(clip_dir):
            shutil.rmtree(clip_dir)
        os.makedirs(clip_dir, exist_ok=True)

        # Filter to valid frame indices
        valid_frames = [
            (frame_idx, bbox)
            for frame_idx, bbox in stored_frames
            if 0 <= frame_idx < len(frame_files)
        ]
        if not valid_frames:
            continue

        # Pass 1: compute max_face_size from bbox metadata only (no imread)
        max_face_size = max(
            max(bbox[2] - bbox[0], bbox[3] - bbox[1]) for _, bbox in valid_frames
        )
        crop_size = max(2, int(max_face_size * 1.5))

        # Pass 2: load one frame at a time, crop, write, release
        crops_manifest: dict[str, tuple[int, int, int, int]] = {}
        actual_sizes: list[tuple[int, int]] = []
        for frame_idx, bbox in valid_frames:
            fname = frame_files[frame_idx]
            frame_path = os.path.join(frames_dir, fname)
            frame = cv2.imread(frame_path)
            if frame is None:
                continue

            h, w = frame.shape[:2]
            cx = (bbox[0] + bbox[2]) / 2
            cy = (bbox[1] + bbox[3]) / 2
            half = crop_size / 2

            x1 = int(max(0, cx - half))
            y1 = int(max(0, cy - half))
            x2 = int(min(w, x1 + crop_size))
            y2 = int(min(h, y1 + crop_size))
            x1 = int(max(0, x2 - crop_size))
            y1 = int(max(0, y2 - crop_size))

            crop = frame[y1:y2, x1:x2]
            cv2.imwrite(os.path.join(clip_dir, fname), crop)
            crops_manifest[fname] = (x1, y1, x2, y2)
            actual_sizes.append((x2 - x1, y2 - y1))

        if not crops_manifest:
            continue

        manifest_width = max(size[0] for size in actual_sizes)
        manifest_height = max(size[1] for size in actual_sizes)
        manifests[face_id] = {
            "clip_dir": clip_dir,
            "crops": crops_manifest,
            "crop_size": (manifest_width, manifest_height),
            "frame_count": len(crops_manifest),
        }

    return manifests


def save_faces_json(faces_data: dict, video_info: dict, output_path: str) -> None:
    data = dict(video_info)
    data["faces"] = faces_data["faces"]
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_faces_json(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)
