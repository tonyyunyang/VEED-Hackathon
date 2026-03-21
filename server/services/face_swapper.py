import os
import shutil
import threading
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np
from insightface.app import FaceAnalysis

_app: FaceAnalysis | None = None
_swapper = None
_onnx_lock = threading.Lock()


def _get_app() -> FaceAnalysis:
    global _app
    if _app is None:
        _app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
        _app.prepare(ctx_id=0, det_size=(640, 640))
    return _app


def _get_swapper():
    global _swapper
    if _swapper is None:
        import insightface
        model_path = os.path.join(
            os.path.dirname(__file__), "..", "models", "inswapper_128.onnx"
        )
        if not os.path.exists(model_path):
            raise FileNotFoundError(
                f"inswapper_128.onnx not found at {model_path}. "
                "Download it and place it in server/models/"
            )
        _swapper = insightface.model_zoo.get_model(model_path)
    return _swapper


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))


def _detect_face_in_frame(frame: np.ndarray, target_embedding: np.ndarray, threshold: float = 0.4):
    """Detect a specific face in a frame by matching embedding.

    Returns the InsightFace face object if found, else None.
    Thread-safe: acquires _onnx_lock around app.get().
    """
    app = _get_app()
    with _onnx_lock:
        detected = app.get(frame)
    for face in detected:
        sim = _cosine_similarity(face.normed_embedding, target_embedding)
        if sim >= threshold:
            return face
    return None


class FaceSwapAdapter(ABC):
    @abstractmethod
    def swap_face(self, frame: np.ndarray, target_face, source_face=None) -> np.ndarray:
        raise NotImplementedError


class InsightFaceSwapAdapter(FaceSwapAdapter):
    def __init__(self, reference_image_path: str | None = None):
        self._source_face = None
        if reference_image_path and os.path.exists(reference_image_path):
            self._load_source(reference_image_path)

    def _load_source(self, image_path: str):
        app = _get_app()
        img = cv2.imread(image_path)
        if img is None:
            return
        faces = app.get(img)
        if faces:
            self._source_face = faces[0]

    def set_source_face(self, face):
        self._source_face = face

    def swap_face(self, frame: np.ndarray, target_face, source_face=None) -> np.ndarray:
        swapper = _get_swapper()
        src = source_face or self._source_face
        if src is None:
            return frame
        with _onnx_lock:
            return swapper.get(frame, target_face, src, paste_back=True)


# ---------------------------------------------------------------------------
# Pipeline: crop → parallel swap → composite
# ---------------------------------------------------------------------------


def crop_face_clips(
    frames_dir: str,
    faces_json: dict,
    selected_face_ids: list[str],
    output_base_dir: str,
    progress_callback=None,
) -> dict[str, dict]:
    """Extract per-face cropped frame sequences from the full frames.

    For each selected face:
    1. Re-detect the face on every frame using embedding matching
    2. Crop a padded square region around the face
    3. Save cropped frames to {output_base_dir}/{face_id}/frame_XXXX.jpg

    Returns a manifest dict per face with crop coordinates for compositing.
    """
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

        # Single pass: detect face, cache frame, collect bboxes
        per_frame_data = {}  # fname -> (frame, face_obj, bbox)
        for fname in frame_files:
            frame = cv2.imread(os.path.join(frames_dir, fname))
            if frame is None:
                continue
            face_obj = _detect_face_in_frame(frame, target_embedding)
            if face_obj is not None:
                per_frame_data[fname] = (frame, face_obj, face_obj.bbox.tolist())

        if not per_frame_data:
            continue

        # Compute consistent crop size from the largest face bbox across all frames
        all_bboxes = [bbox for _, _, bbox in per_frame_data.values()]
        max_face_size = max(
            max(b[2] - b[0], b[3] - b[1]) for b in all_bboxes
        )
        crop_size = int(max_face_size * 1.5)

        # Crop each frame at a square region centered on the face
        crops_manifest = {}
        for fname, (frame, face_obj, bbox) in per_frame_data.items():
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

        actual_crop_h = y2 - y1
        actual_crop_w = x2 - x1

        manifests[face_id] = {
            "crop_dir": clip_dir,
            "crops": crops_manifest,
            "crop_size": (actual_crop_w, actual_crop_h),
        }

    if progress_callback:
        progress_callback(1.0)

    return manifests


def swap_single_face_clip(
    clip_dir: str,
    output_dir: str,
    target_embedding: np.ndarray,
    adapter: FaceSwapAdapter,
    progress_callback=None,
) -> None:
    """Run face swap on a single face's cropped clip frames.

    Reads cropped frames from clip_dir, detects the face in each crop,
    swaps it, and writes the result to output_dir with the same filenames.
    """
    os.makedirs(output_dir, exist_ok=True)

    frame_files = sorted(
        f for f in os.listdir(clip_dir)
        if f.startswith("frame_") and f.endswith(".jpg")
    )
    total = len(frame_files)

    for i, fname in enumerate(frame_files):
        crop = cv2.imread(os.path.join(clip_dir, fname))
        if crop is None:
            continue

        with _onnx_lock:
            detected = _get_app().get(crop)
        for det_face in detected:
            sim = _cosine_similarity(det_face.normed_embedding, target_embedding)
            if sim >= 0.4:
                crop = adapter.swap_face(crop, det_face)
                break

        cv2.imwrite(os.path.join(output_dir, fname), crop)

        if progress_callback and total > 0:
            progress_callback((i + 1) / total)


def composite_swapped_faces(
    frames_dir: str,
    output_dir: str,
    manifests: dict[str, dict],
    swapped_base_dir: str,
) -> None:
    """Composite swapped face crops back onto original frames.

    For each frame, copies the original, then pastes each face's swapped crop
    at the recorded position.
    """
    os.makedirs(output_dir, exist_ok=True)

    # Collect all frame filenames (including ones with no face — pass through)
    all_frame_files = set()
    for face_id, manifest in manifests.items():
        all_frame_files.update(manifest["crops"].keys())
    for f in os.listdir(frames_dir):
        if f.startswith("frame_") and f.endswith(".jpg"):
            all_frame_files.add(f)

    for fname in sorted(all_frame_files):
        frame = cv2.imread(os.path.join(frames_dir, fname))
        if frame is None:
            continue

        for face_id, manifest in manifests.items():
            if fname not in manifest["crops"]:
                continue

            swapped_crop_path = os.path.join(swapped_base_dir, face_id, fname)
            if not os.path.exists(swapped_crop_path):
                continue

            swapped_crop = cv2.imread(swapped_crop_path)
            if swapped_crop is None:
                continue

            x1, y1, x2, y2 = manifest["crops"][fname]
            region_h = y2 - y1
            region_w = x2 - x1
            crop_h, crop_w = swapped_crop.shape[:2]
            if crop_h != region_h or crop_w != region_w:
                swapped_crop = cv2.resize(swapped_crop, (region_w, region_h))

            frame[y1:y2, x1:x2] = swapped_crop

        cv2.imwrite(os.path.join(output_dir, fname), frame)


def swap_faces_pipeline(
    frames_dir: str,
    output_dir: str,
    faces_json: dict,
    selected_face_ids: list[str],
    adapter: FaceSwapAdapter | None = None,
    progress_callback=None,
) -> None:
    """Full face swap pipeline: crop per-face clips -> swap in parallel -> composite.

    Drop-in replacement for the old swap_faces_in_video (same parameter signature).
    """
    if adapter is None:
        adapter = InsightFaceSwapAdapter()

    base_dir = os.path.dirname(frames_dir)  # e.g., server/storage/{video_id}
    clips_dir = os.path.join(base_dir, "face_clips")
    swapped_clips_dir = os.path.join(base_dir, "swapped_clips")

    # Phase 1: Crop per-face clips
    if progress_callback:
        progress_callback(0.0)

    manifests = crop_face_clips(
        frames_dir, faces_json, selected_face_ids, clips_dir
    )

    if progress_callback:
        progress_callback(0.2)

    if not manifests:
        # No faces detected in any frame — copy originals through
        os.makedirs(output_dir, exist_ok=True)
        for f in os.listdir(frames_dir):
            if f.startswith("frame_") and f.endswith(".jpg"):
                shutil.copy2(os.path.join(frames_dir, f), os.path.join(output_dir, f))
        if progress_callback:
            progress_callback(1.0)
        return

    # Phase 2: Swap each face clip in parallel
    face_ids_to_process = list(manifests.keys())
    total_faces = len(face_ids_to_process)

    def face_progress(face_idx):
        def callback(p):
            overall = 0.2 + 0.6 * (face_idx + p) / total_faces
            if progress_callback:
                progress_callback(overall)
        return callback

    def swap_one_face(args):
        face_id, idx = args
        face_data = faces_json["faces"][face_id]
        target_embedding = np.array(face_data["embedding"])
        clip_dir = manifests[face_id]["crop_dir"]
        swap_out = os.path.join(swapped_clips_dir, face_id)
        swap_single_face_clip(
            clip_dir, swap_out, target_embedding, adapter, face_progress(idx)
        )

    with ThreadPoolExecutor(max_workers=min(total_faces, 4)) as executor:
        executor.map(swap_one_face, [(fid, i) for i, fid in enumerate(face_ids_to_process)])

    if progress_callback:
        progress_callback(0.8)

    # Phase 3: Composite swapped faces back onto original frames
    composite_swapped_faces(frames_dir, output_dir, manifests, swapped_clips_dir)

    if progress_callback:
        progress_callback(1.0)
