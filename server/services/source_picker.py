"""
Source image selection from the picture library.

Given a face crop from a video, finds the most similar face in
picture_example/ using InsightFace embeddings + cosine similarity.

Completely independent from face tracking — only needs an image path.

Fallback on any error: returns the first library image (alphabetical).
"""

import os

import cv2
import numpy as np

from config import PICTURE_LIBRARY_DIR, DUMMY_TRACKING

if not DUMMY_TRACKING:
    from insightface.app import FaceAnalysis

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

_face_analyser = None

# Computed once at first call, then reused for every pick_source() call.
_library_embeddings: list[tuple[str, np.ndarray]] | None = None


# ── InsightFace setup ────────────────────────────────────────────────────


def _get_face_analyser():
    global _face_analyser
    if _face_analyser is None:
        _face_analyser = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
        _face_analyser.prepare(ctx_id=0, det_size=(640, 640))
    return _face_analyser


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))


# ── Library helpers ──────────────────────────────────────────────────────


def _list_library_images() -> list[str]:
    """Return sorted absolute paths of every image in picture_example/."""
    if not os.path.isdir(PICTURE_LIBRARY_DIR):
        return []
    return sorted(
        os.path.join(PICTURE_LIBRARY_DIR, f)
        for f in os.listdir(PICTURE_LIBRARY_DIR)
        if os.path.splitext(f)[1].lower() in IMAGE_EXTS
    )


def _build_library_embeddings() -> list[tuple[str, np.ndarray]]:
    """Detect the first face in each library image and store its embedding.

    Called once, then cached in _library_embeddings.
    Images with no detectable face are silently skipped.
    """
    global _library_embeddings
    if _library_embeddings is not None:
        return _library_embeddings

    analyser = _get_face_analyser()
    _library_embeddings = []

    for image_path in _list_library_images():
        image = cv2.imread(image_path)
        if image is None:
            continue
        faces = analyser.get(image)
        if faces:
            _library_embeddings.append((image_path, faces[0].normed_embedding))

    return _library_embeddings


def _extract_embedding(image_path: str) -> np.ndarray | None:
    """Return the face embedding of the first face found in *image_path*."""
    analyser = _get_face_analyser()
    image = cv2.imread(image_path)
    if image is None:
        return None
    faces = analyser.get(image)
    return faces[0].normed_embedding if faces else None


# ── Public API ───────────────────────────────────────────────────────────


def pick_source(face_crop_path: str) -> str:
    """Choose the library image whose face is closest to *face_crop_path*.

    Pipeline:
      1. Extract embedding from the video face crop
      2. Compare (cosine similarity) against every library face
      3. Return the path of the highest-scoring match

    Returns:
        Absolute path to the best matching library image.

    Raises:
        FileNotFoundError: if picture_example/ is empty.
    """
    library_images = _list_library_images()
    if not library_images:
        raise FileNotFoundError(f"No images in picture library: {PICTURE_LIBRARY_DIR}")

    first_image = library_images[0]  # fallback for every error path

    # Dummy mode: no InsightFace available — always return first image
    if DUMMY_TRACKING:
        return first_image

    try:
        video_face_embedding = _extract_embedding(face_crop_path)
        if video_face_embedding is None:
            return first_image

        library = _build_library_embeddings()
        if not library:
            return first_image

        # Find the library face with the highest cosine similarity
        best_match_path = first_image
        best_similarity = -1.0
        for library_path, library_embedding in library:
            similarity = _cosine_similarity(video_face_embedding, library_embedding)
            if similarity > best_similarity:
                best_similarity = similarity
                best_match_path = library_path

        return best_match_path

    except Exception:
        return first_image
