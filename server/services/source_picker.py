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

from VEEDHackathon.server.config import PICTURE_LIBRARY_DIR, DUMMY_TRACKING
from sklearn.metrics.pairwise import cosine_similarity

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
            similarity = cosine_similarity(
                video_face_embedding.reshape(1, -1),
                library_embedding.reshape(1, -1),
            )[0, 0]
            if similarity > best_similarity:
                best_similarity = similarity
                best_match_path = library_path

        return best_match_path

    except Exception:
        return first_image


if __name__ == "__main__":
    images = _list_library_images()
    if not images:
        print("No images found in picture library")
        raise SystemExit(1)

    test_image = images[0]
    print(f"Test image: {os.path.basename(test_image)}")
    print(f"Library: {len(images)} images\n")

    # Extract test image embedding
    test_embedding = _extract_embedding(test_image)
    if test_embedding is None:
        print("No face detected in test image")
        raise SystemExit(1)

    # Test 1: compare against full library (should find itself)
    print("── Test 1: Full library (should match itself) ──")
    library = _build_library_embeddings()
    ranked = []
    for path, emb in library:
        sim = cosine_similarity(
            test_embedding.reshape(1, -1), emb.reshape(1, -1)
        )[0, 0]
        ranked.append((sim, path))
    ranked.sort(reverse=True)

    for i, (sim, path) in enumerate(ranked):
        tag = " ← TEST IMAGE" if path == test_image else ""
        print(f"  {i + 1}. {os.path.basename(path):>20s}  sim={sim:.4f}{tag}")

    assert ranked[0][1] == test_image, "FAIL: did not match itself as #1"
    print("  ✓ Correctly matched itself\n")

    # Test 2: compare against library minus the test image
    print("── Test 2: Library without test image (closest match) ──")
    filtered = [(path, emb) for path, emb in library if path != test_image]
    ranked2 = []
    for path, emb in filtered:
        sim = cosine_similarity(
            test_embedding.reshape(1, -1), emb.reshape(1, -1)
        )[0, 0]
        ranked2.append((sim, path))
    ranked2.sort(reverse=True)

    for i, (sim, path) in enumerate(ranked2):
        print(f"  {i + 1}. {os.path.basename(path):>20s}  sim={sim:.4f}")

    print(f"\n  Best match (excluding self): {os.path.basename(ranked2[0][1])} (sim={ranked2[0][0]:.4f})")
