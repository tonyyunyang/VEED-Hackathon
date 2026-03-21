import os
import json
import base64
import random
from collections import defaultdict

import cv2
import numpy as np

from config import DUMMY_TRACKING

if not DUMMY_TRACKING:
    from insightface.app import FaceAnalysis

_app = None


def _get_app():
    global _app
    if _app is None:
        _app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
        _app.prepare(ctx_id=0, det_size=(640, 640))
    return _app


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))


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


def _dummy_detect_and_cluster(
    frames_dir: str, storage_dir: str, subsample: int = 5
) -> dict:
    """Return 3 random square bounding boxes as fake faces for frontend dev."""
    frame_files = sorted(
        f for f in os.listdir(frames_dir) if f.startswith("frame_") and f.endswith(".jpg")
    )
    if not frame_files:
        return {"faces": {}}

    # Read first frame to get dimensions
    sample = cv2.imread(os.path.join(frames_dir, frame_files[0]))
    if sample is None:
        return {"faces": {}}
    h, w = sample.shape[:2]

    rng = random.Random(42)  # deterministic so reloads are stable
    face_size = min(h, w) // 5  # square side length

    faces_data = {}
    for idx in range(3):
        face_id = f"face_{idx}"
        # Pick a random position that fits within the frame
        x1 = rng.randint(0, max(0, w - face_size))
        y1 = rng.randint(0, max(0, h - face_size))
        x2 = x1 + face_size
        y2 = y1 + face_size
        bbox = [float(x1), float(y1), float(x2), float(y2)]

        # Build frames dict — assign this box to every subsampled frame
        frames_dict = {}
        for i, fname in enumerate(frame_files):
            if i % subsample != 0:
                continue
            frames_dict[str(i)] = bbox

        # Thumbnail from the first frame
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


def detect_and_cluster(
    frames_dir: str, storage_dir: str, subsample: int = 5
) -> dict:
    if DUMMY_TRACKING:
        return _dummy_detect_and_cluster(frames_dir, storage_dir, subsample)

    app = _get_app()
    frame_files = sorted(
        f for f in os.listdir(frames_dir) if f.startswith("frame_") and f.endswith(".jpg")
    )

    detections: list[tuple[int, object]] = []
    frame_cache: dict[int, np.ndarray] = {}

    for i, fname in enumerate(frame_files):
        if i % subsample != 0:
            continue
        frame_path = os.path.join(frames_dir, fname)
        frame = cv2.imread(frame_path)
        if frame is None:
            continue
        frame_cache[i] = frame
        faces = app.get(frame)
        for face in faces:
            detections.append((i, face))

    if not detections:
        return {"faces": {}}

    clusters: list[list[tuple[int, object]]] = []
    similarity_threshold = 0.4

    for frame_idx, face in detections:
        emb = face.normed_embedding
        matched = False
        for cluster in clusters:
            rep_emb = cluster[0][1].normed_embedding
            if _cosine_similarity(emb, rep_emb) >= similarity_threshold:
                cluster.append((frame_idx, face))
                matched = True
                break
        if not matched:
            clusters.append([(frame_idx, face)])

    faces_data = {}
    for cluster_idx, cluster in enumerate(clusters):
        face_id = f"face_{cluster_idx}"
        ages = [f.age for _, f in cluster]
        genders = [f.gender for _, f in cluster]

        best_idx, best_face = max(
            cluster,
            key=lambda x: (x[1].bbox[2] - x[1].bbox[0]) * (x[1].bbox[3] - x[1].bbox[1])
        )
        best_frame = frame_cache.get(best_idx)
        thumbnail = ""
        if best_frame is not None:
            thumbnail = _crop_face_thumbnail(best_frame, best_face.bbox.tolist())

        thumb_path = f"{face_id}_thumb.jpg"
        if best_frame is not None:
            x1, y1, x2, y2 = [int(v) for v in best_face.bbox]
            h, w = best_frame.shape[:2]
            crop = best_frame[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
            if crop.size > 0:
                cv2.imwrite(os.path.join(storage_dir, thumb_path), crop)

        frames_dict = {}
        for frame_idx, face in cluster:
            frames_dict[str(frame_idx)] = face.bbox.tolist()

        avg_age = int(np.mean(ages))
        gender_counts = defaultdict(int)
        for g in genders:
            gender_counts[g] += 1
        raw_gender = max(gender_counts, key=gender_counts.get)
        # InsightFace returns gender as int (0=female, 1=male) or str
        if isinstance(raw_gender, (int, np.integer)):
            majority_gender = "male" if int(raw_gender) == 1 else "female"
        else:
            majority_gender = str(raw_gender)

        faces_data[face_id] = {
            "age": avg_age,
            "gender": majority_gender,
            "thumbnail": thumbnail,
            "thumbnail_path": thumb_path,
            "embedding": cluster[0][1].normed_embedding.tolist(),
            "frames": frames_dict,
            "frame_count": len(frames_dict),
        }

    return {"faces": faces_data}


def save_faces_json(faces_data: dict, video_info: dict, output_path: str) -> None:
    data = {
        "fps": video_info["fps"],
        "total_frames": video_info["total_frames"],
        "faces": faces_data["faces"],
    }
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)


def load_faces_json(path: str) -> dict:
    with open(path) as f:
        return json.load(f)
