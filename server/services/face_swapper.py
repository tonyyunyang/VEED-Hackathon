import os
import shutil
import threading
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np
from insightface.app import FaceAnalysis
import insightface

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
# Pipeline: swap pre-cropped clips → composite back
# ---------------------------------------------------------------------------


def swap_single_face_clip(
        clip_dir: str,
        output_dir: str,
        target_embedding: np.ndarray,
        adapter: FaceSwapAdapter,
        progress_callback=None,
) -> None:
    """Run face swap on a single face's cropped clip frames.

    Reads cropped frames from clip_dir (produced by face_tracker.extract_face_clips),
    detects the face in each crop, swaps it, writes result to output_dir.
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

    For each frame, reads the original, pastes each face's swapped crop
    at the recorded position, writes the result.
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
        manifests: dict[str, dict],
        faces_json: dict,
        frames_dir: str,
        output_dir: str,
        adapter: FaceSwapAdapter | None = None,
        progress_callback=None,
) -> None:
    """Swap faces in pre-cropped clips and composite back onto original frames.

    Args:
        manifests: from face_tracker.extract_face_clips() — clip dirs + crop coords
        faces_json: loaded faces.json with embeddings
        frames_dir: original full frames directory
        output_dir: where to write final composited frames
        adapter: face swap adapter (defaults to InsightFaceSwapAdapter)
        progress_callback: called with float 0.0-1.0
    """
    if adapter is None:
        adapter = InsightFaceSwapAdapter()

    base_dir = os.path.dirname(frames_dir)
    swapped_clips_dir = os.path.join(base_dir, "swapped_clips")

    if progress_callback:
        progress_callback(0.0)

    if not manifests:
        # No face clips — copy originals through unchanged
        os.makedirs(output_dir, exist_ok=True)
        for f in os.listdir(frames_dir):
            if f.startswith("frame_") and f.endswith(".jpg"):
                shutil.copy2(os.path.join(frames_dir, f), os.path.join(output_dir, f))
        if progress_callback:
            progress_callback(1.0)
        return

    # Phase 1: Swap each face clip in parallel
    face_ids_to_process = list(manifests.keys())
    total_faces = len(face_ids_to_process)

    def face_progress(face_idx):
        def callback(p):
            overall = 0.7 * (face_idx + p) / total_faces
            if progress_callback:
                progress_callback(overall)

        return callback

    def swap_one_face(args):
        face_id, idx = args
        face_data = faces_json["faces"][face_id]
        target_embedding = np.array(face_data["embedding"])
        clip_dir = manifests[face_id]["clip_dir"]
        swap_out = os.path.join(swapped_clips_dir, face_id)
        swap_single_face_clip(
            clip_dir, swap_out, target_embedding, adapter, face_progress(idx)
        )

    with ThreadPoolExecutor(max_workers=min(total_faces, 4)) as executor:
        list(executor.map(swap_one_face, [(fid, i) for i, fid in enumerate(face_ids_to_process)]))

    if progress_callback:
        progress_callback(0.7)

    # Phase 2: Composite swapped faces back onto original frames
    composite_swapped_faces(frames_dir, output_dir, manifests, swapped_clips_dir)

    if progress_callback:
        progress_callback(1.0)


if __name__ == "__main__":
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from services import video as video_service
    from services.face_tracker import detect_and_cluster, save_faces_json, load_faces_json, extract_face_clips

    # Usage: python -m services.face_swapper <video_path> [output_dir]
    if len(sys.argv) < 2:
        print("Usage: python -m services.face_swapper <video_path> [output_dir]")
        print("  video_path: path to an .mp4/.mov/.webm video file")
        print("  output_dir: where to write results (default: server/test_swap_output/)")
        sys.exit(1)

    VIDEO_PATH = os.path.abspath(sys.argv[1])
    if not os.path.exists(VIDEO_PATH):
        print(f"Error: video not found: {VIDEO_PATH}")
        sys.exit(1)

    TEST_DIR = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(__file__), "..", "test_swap_output")
    TEST_DIR = os.path.abspath(TEST_DIR)

    os.makedirs(TEST_DIR, exist_ok=True)
    frames_dir = os.path.join(TEST_DIR, "frames")
    swapped_dir = os.path.join(TEST_DIR, "swapped")
    faces_json_path = os.path.join(TEST_DIR, "faces.json")

    # Step 1: Extract frames + audio
    print(f"[1/6] Extracting frames from {VIDEO_PATH}...")
    video_info = video_service.extract_frames(VIDEO_PATH, frames_dir)
    fps = video_info["fps"]
    print(f"       {video_info['total_frames']} frames at {fps} fps")

    audio_path = os.path.join(TEST_DIR, "audio.aac")
    video_service.extract_audio(VIDEO_PATH, audio_path)

    # Step 2: Detect & cluster faces
    print("[2/6] Detecting faces...")
    faces_data = detect_and_cluster(frames_dir, TEST_DIR, subsample=5)
    save_faces_json(faces_data, video_info, faces_json_path)
    faces_json = load_faces_json(faces_json_path)

    face_ids = list(faces_json["faces"].keys())
    print(f"       Found {len(face_ids)} face(s): {face_ids}")
    if not face_ids:
        print("No faces found. Exiting.")
        sys.exit(1)

    # Swap the first detected face
    selected = [face_ids[0]]
    print(f"       Swapping: {selected}")

    # Step 3: Extract face clips (face_tracker responsibility)
    print("[3/6] Extracting face clips...")
    clips_dir = os.path.join(TEST_DIR, "face_clips")
    manifests = extract_face_clips(frames_dir, faces_json, selected, clips_dir)
    print(f"       Created clips for {list(manifests.keys())}")

    # Step 4: Swap faces in clips (face_swapper responsibility)
    print("[4/6] Swapping faces in clips...")

    def on_progress(p):
        print(f"       progress: {p:.0%}", end="\r")

    swap_faces_pipeline(manifests, faces_json, frames_dir, swapped_dir, progress_callback=on_progress)
    print()

    # Step 5: Reassemble original video
    original_out = os.path.join(TEST_DIR, "original_reassembled.mp4")
    print("[5/6] Reassembling original video...")
    video_service.reassemble_video(
        frames_dir,
        audio_path if os.path.exists(audio_path) else None,
        original_out,
        fps,
    )

    # Step 6: Reassemble swapped video
    swapped_out = os.path.join(TEST_DIR, "swapped_output.mp4")
    print("[6/6] Reassembling swapped video...")
    video_service.reassemble_video(
        swapped_dir,
        audio_path if os.path.exists(audio_path) else None,
        swapped_out,
        fps,
    )

    print()
    print("Done! Output files:")
    print(f"  Original: {original_out}")
    print(f"  Swapped:  {swapped_out}")
