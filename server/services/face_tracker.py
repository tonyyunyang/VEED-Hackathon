"""
Face detection and clustering from video frames.

Only identifies and groups faces — no source selection, no swapping.

Output per face:
  - thumbnail    : base64 data-URI for the UI
  - thumbnail_path : small JPEG on disk
  - crop_path      : high-quality padded crop (used by source_picker for matching)
  - age, gender, frame_count
"""

import os
import json
import base64
import random
from collections import Counter

import cv2
import numpy as np

from config import DUMMY_TRACKING

if not DUMMY_TRACKING:
    from insightface.app import FaceAnalysis

_face_analyser = None

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
SIMILARITY_THRESHOLD = 0.4


def _get_face_analyser():
    """Lazy-init the InsightFace model (heavy, only loaded once)."""
    global _face_analyser
    if _face_analyser is None:
        _face_analyser = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
        _face_analyser.prepare(ctx_id=0, det_size=(640, 640))
    return _face_analyser


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))


# ── Image helpers ────────────────────────────────────────────────────────


def _list_frame_files(frames_dir: str) -> list[str]:
    """Return sorted frame filenames (frame_0001.jpg, frame_0002.jpg, …)."""
    return sorted(
        f for f in os.listdir(frames_dir)
        if f.startswith("frame_") and f.endswith(".jpg")
    )


def _make_base64_thumbnail(frame: np.ndarray, bbox: list[float], size: int = 112) -> str:
    """Crop the face from *frame*, resize to *size*×*size*, return as base64 data-URI."""
    x1, y1, x2, y2 = [int(v) for v in bbox]
    h, w = frame.shape[:2]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        return ""
    crop = cv2.resize(crop, (size, size))
    _, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return f"data:image/jpeg;base64,{base64.b64encode(buf).decode()}"


def _save_padded_face_crop(
    frame: np.ndarray, bbox, output_dir: str, filename: str
) -> None:
    """Save a high-quality face crop with generous padding around the bbox.

    Used downstream by source_picker to compare against the picture library.
    """
    x1, y1, x2, y2 = [int(v) for v in bbox]
    h, w = frame.shape[:2]
    padding = max(x2 - x1, y2 - y1)  # pad by 1× the face size in each direction
    crop = frame[
        max(0, y1 - padding): min(h, y2 + padding),
        max(0, x1 - padding): min(w, x2 + padding),
    ]
    if crop.size > 0:
        cv2.imwrite(
            os.path.join(output_dir, filename), crop, [cv2.IMWRITE_JPEG_QUALITY, 95]
        )


def _majority_gender(genders: list) -> str:
    """Return the most common gender label, normalised to 'male'/'female'."""
    raw = Counter(genders).most_common(1)[0][0]
    if isinstance(raw, (int, np.integer)):
        return "male" if int(raw) == 1 else "female"
    return str(raw)


# ── Dummy mode (frontend development without InsightFace) ────────────────


def _dummy_detect_and_cluster(
    frames_dir: str, storage_dir: str, subsample: int = 5
) -> dict:
    """Generate 3 fake faces with random bounding boxes (deterministic seed)."""
    frame_files = _list_frame_files(frames_dir)
    if not frame_files:
        return {"faces": {}}

    first_frame = cv2.imread(os.path.join(frames_dir, frame_files[0]))
    if first_frame is None:
        return {"faces": {}}
    frame_h, frame_w = first_frame.shape[:2]

    rng = random.Random(42)
    face_size = min(frame_h, frame_w) // 5
    num_sampled_frames = sum(1 for i in range(len(frame_files)) if i % subsample == 0)

    faces = {}
    for idx in range(3):
        face_id = f"face_{idx}"
        x1 = rng.randint(0, max(0, frame_w - face_size))
        y1 = rng.randint(0, max(0, frame_h - face_size))
        bbox = [float(x1), float(y1), float(x1 + face_size), float(y1 + face_size)]

        thumb_filename = f"{face_id}_thumb.jpg"
        crop_filename = f"{face_id}_crop.jpg"

        crop = first_frame[y1:y1 + face_size, x1:x1 + face_size]
        if crop.size > 0:
            cv2.imwrite(os.path.join(storage_dir, thumb_filename), crop)
        _save_padded_face_crop(first_frame, bbox, storage_dir, crop_filename)

        faces[face_id] = {
            "age": rng.randint(20, 45),
            "gender": rng.choice(["male", "female"]),
            "thumbnail": _make_base64_thumbnail(first_frame, bbox),
            "thumbnail_path": thumb_filename,
            "crop_path": crop_filename,
            "frame_count": num_sampled_frames,
        }

    return {"faces": faces}


# ── Real detection ───────────────────────────────────────────────────────


def detect_and_cluster(
    frames_dir: str, storage_dir: str, subsample: int = 5
) -> dict:
    """Detect faces across sub-sampled frames, cluster by identity.

    Returns {"faces": {"face_0": {...}, "face_1": {...}, ...}}.
    """
    if DUMMY_TRACKING:
        return _dummy_detect_and_cluster(frames_dir, storage_dir, subsample)

    analyser = _get_face_analyser()
    frame_files = _list_frame_files(frames_dir)

    # ── 1. Detect every face on every sub-sampled frame ──────────────────
    all_detections: list[tuple[int, object]] = []  # (frame_index, insightface_object)
    frame_by_index: dict[int, np.ndarray] = {}

    for frame_index, filename in enumerate(frame_files):
        if frame_index % subsample != 0:
            continue
        frame = cv2.imread(os.path.join(frames_dir, filename))
        if frame is None:
            continue
        frame_by_index[frame_index] = frame
        for face in analyser.get(frame):
            all_detections.append((frame_index, face))

    if not all_detections:
        return {"faces": {}}

    # ── 2. Cluster detections by identity (greedy cosine matching) ───────
    identity_clusters: list[list[tuple[int, object]]] = []

    for frame_index, face in all_detections:
        embedding = face.normed_embedding
        placed = False
        for cluster in identity_clusters:
            representative_embedding = cluster[0][1].normed_embedding
            if _cosine_similarity(embedding, representative_embedding) >= SIMILARITY_THRESHOLD:
                cluster.append((frame_index, face))
                placed = True
                break
        if not placed:
            identity_clusters.append([(frame_index, face)])

    # ── 3. Build output dict per identity ────────────────────────────────
    faces_output = {}

    for cluster_index, cluster in enumerate(identity_clusters):
        face_id = f"face_{cluster_index}"

        # Pick the detection with the largest bounding-box area (best quality)
        best_frame_index, best_detection = max(
            cluster,
            key=lambda det: (det[1].bbox[2] - det[1].bbox[0]) * (det[1].bbox[3] - det[1].bbox[1]),
        )
        best_frame = frame_by_index.get(best_frame_index)

        thumb_filename = f"{face_id}_thumb.jpg"
        crop_filename = f"{face_id}_crop.jpg"
        thumbnail_b64 = ""

        if best_frame is not None:
            bbox = best_detection.bbox.tolist()
            thumbnail_b64 = _make_base64_thumbnail(best_frame, bbox)

            # Save small thumbnail (tight crop)
            bx1, by1, bx2, by2 = [int(v) for v in bbox]
            fh, fw = best_frame.shape[:2]
            tight_crop = best_frame[max(0, by1):min(fh, by2), max(0, bx1):min(fw, bx2)]
            if tight_crop.size > 0:
                cv2.imwrite(os.path.join(storage_dir, thumb_filename), tight_crop)

            # Save padded crop (for source_picker matching)
            _save_padded_face_crop(best_frame, bbox, storage_dir, crop_filename)

        faces_output[face_id] = {
            "age": int(np.mean([det.age for _, det in cluster])),
            "gender": _majority_gender([det.gender for _, det in cluster]),
            "thumbnail": thumbnail_b64,
            "thumbnail_path": thumb_filename,
            "crop_path": crop_filename,
            "frame_count": len(cluster),
        }

    return {"faces": faces_output}


# ── JSON persistence ─────────────────────────────────────────────────────


def save_faces_json(faces_data: dict, video_info: dict, output_path: str) -> None:
    with open(output_path, "w") as f:
        json.dump(
            {"fps": video_info["fps"], "total_frames": video_info["total_frames"],
             "faces": faces_data["faces"]},
            f, indent=2,
        )


def load_faces_json(path: str) -> dict:
    with open(path) as f:
        return json.load(f)
