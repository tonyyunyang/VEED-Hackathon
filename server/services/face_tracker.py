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

        thumbnail = _crop_face_thumbnail(sample, bbox)
        thumb_path = f"{face_id}_thumb.jpg"

        crop = sample[y1:y2, x1:x2]
        if crop.size > 0:
            cv2.imwrite(os.path.join(storage_dir, thumb_path), crop)

        # Use first library image as source (dummy mode has no embeddings)
        library_images = _get_library_images()
        source_path = library_images[0] if library_images else f"{face_id}_source.jpg"
        if not library_images:
            raise Exception("no source images provided")

        sampled_count = sum(1 for i in range(len(frame_files)) if i % subsample == 0)
        faces_data[face_id] = {
            "age": rng.randint(20, 45),
            "gender": rng.choice(["male", "female"]),
            "thumbnail": thumbnail,
            "thumbnail_path": thumb_path,
            "source_path": source_path,
            "frame_count": sampled_count,
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
        thumb_path = f"{face_id}_thumb.jpg"
        if best_frame is not None:
            thumbnail = _crop_face_thumbnail(best_frame, best_face.bbox.tolist())
            x1, y1, x2, y2 = [int(v) for v in best_face.bbox]
            h, w = best_frame.shape[:2]
            crop = best_frame[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
            if crop.size > 0:
                cv2.imwrite(os.path.join(storage_dir, thumb_path), crop)

        # Pick source from picture library (closest face match)
        face_embedding = cluster[0][1].normed_embedding
        library_match = find_closest_library_face(face_embedding)
        if library_match:
            source_path = library_match
        else:
            raise Exception

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
            "source_path": source_path,
            "frame_count": len(cluster),
        }

    return {"faces": faces_data}


def extract_face_clips(
        frames_dir: str,
        faces_json: dict,
        selected_face_ids: list[str],
        output_base_dir: str,
) -> dict[str, dict]:
    """Extract per-face cropped frame sequences from full frames.

    For each selected face:
    1. Re-detect the face on every frame using embedding matching
    2. Crop a padded square region around the face
    3. Save cropped frames to {output_base_dir}/{face_id}/frame_XXXX.jpg

    Returns a manifest dict:
    {
        "face_0": {
            "clip_dir": "/path/to/face_0/",
            "crops": {
                "frame_0001.jpg": (x1, y1, x2, y2),
            },
            "crop_size": (width, height),
        }
    }
    """
    app = _get_app()
    frame_files = sorted(
        f for f in os.listdir(frames_dir)
        if f.startswith("frame_") and f.endswith(".jpg")
    )
    manifests = {}

    for face_id in selected_face_ids:
        face_data = faces_json["faces"][face_id]
        target_embedding = np.array(face_data["embedding"])

        clip_dir = os.path.join(output_base_dir, face_id)
        os.makedirs(clip_dir, exist_ok=True)

        # Single pass: detect face on every frame, cache frame + bbox
        per_frame_data = {}  # fname -> (frame, bbox)
        for fname in frame_files:
            frame = cv2.imread(os.path.join(frames_dir, fname))
            if frame is None:
                continue
            detected = app.get(frame)
            for face in detected:
                sim = _cosine_similarity(face.normed_embedding, target_embedding)
                if sim >= 0.4:
                    per_frame_data[fname] = (frame, face.bbox.tolist())
                    break

        if not per_frame_data:
            continue

        # Compute consistent crop size from the largest face across all frames
        all_bboxes = [bbox for _, bbox in per_frame_data.values()]
        max_face_size = max(
            max(b[2] - b[0], b[3] - b[1]) for b in all_bboxes
        )
        crop_size = int(max_face_size * 1.5)

        # Crop each frame at a square region centered on the face
        crops_manifest = {}
        for fname, (frame, bbox) in per_frame_data.items():
            h, w = frame.shape[:2]

            cx = (bbox[0] + bbox[2]) / 2
            cy = (bbox[1] + bbox[3]) / 2
            half = crop_size / 2

            x1 = int(max(0, cx - half))
            y1 = int(max(0, cy - half))
            x2 = int(min(w, x1 + crop_size))
            y2 = int(min(h, y1 + crop_size))
            # Adjust start if crop was clamped at the end
            x1 = int(max(0, x2 - crop_size))
            y1 = int(max(0, y2 - crop_size))

            crop = frame[y1:y2, x1:x2]
            cv2.imwrite(os.path.join(clip_dir, fname), crop)
            crops_manifest[fname] = (x1, y1, x2, y2)

        actual_h = y2 - y1
        actual_w = x2 - x1

        manifests[face_id] = {
            "clip_dir": clip_dir,
            "crops": crops_manifest,
            "crop_size": (actual_w, actual_h),
        }

    return manifests


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
