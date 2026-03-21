import os
from abc import ABC, abstractmethod

import cv2
import numpy as np
from insightface.app import FaceAnalysis

_app: FaceAnalysis | None = None
_swapper = None


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
        return swapper.get(frame, target_face, src, paste_back=True)


def swap_faces_in_video(
    frames_dir: str,
    output_dir: str,
    faces_json: dict,
    selected_face_ids: list[str],
    adapter: FaceSwapAdapter | None = None,
    progress_callback=None,
) -> None:
    os.makedirs(output_dir, exist_ok=True)
    app = _get_app()

    if adapter is None:
        adapter = InsightFaceSwapAdapter()

    selected_faces = {
        fid: faces_json["faces"][fid]
        for fid in selected_face_ids
        if fid in faces_json["faces"]
    }

    frame_files = sorted(
        f for f in os.listdir(frames_dir)
        if f.startswith("frame_") and f.endswith(".jpg")
    )
    total = len(frame_files)

    for i, fname in enumerate(frame_files):
        frame_path = os.path.join(frames_dir, fname)
        frame = cv2.imread(frame_path)
        if frame is None:
            continue

        detected = app.get(frame)

        for face_id, face_data in selected_faces.items():
            target_embedding = np.array(face_data["embedding"])
            for det_face in detected:
                sim = _cosine_similarity(det_face.normed_embedding, target_embedding)
                if sim >= 0.4:
                    frame = adapter.swap_face(frame, det_face)
                    break

        cv2.imwrite(os.path.join(output_dir, fname), frame)

        if progress_callback and total > 0:
            progress_callback((i + 1) / total)
