import os

import cv2
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from ..config import PICTURE_LIBRARY_DIR

_library_cache: list[tuple[str, np.ndarray]] | None = None  # [(path, embedding), ...]


def _get_library_images() -> list[str]:
    """Return sorted list of image paths from the picture library."""
    if not os.path.isdir(PICTURE_LIBRARY_DIR):
        return []
    exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
    return sorted(
        os.path.join(PICTURE_LIBRARY_DIR, f)
        for f in os.listdir(PICTURE_LIBRARY_DIR)
        if os.path.splitext(f)[1].lower() in exts
    )


def _get_library_embeddings() -> list[tuple[str, np.ndarray]]:
    """Load and cache face embeddings for all library images."""
    global _library_cache
    if _library_cache is not None:
        return _library_cache

    app = _get_app()
    _library_cache = []
    for path in _get_library_images():
        img = cv2.imread(path)
        if img is None:
            continue
        faces = app.get(img)
        if faces:
            _library_cache.append((path, faces[0].normed_embedding))
    return _library_cache


def find_closest_library_face(face_embedding: np.ndarray) -> str | None:
    """Find the library image whose face is most similar to the given embedding.

    Returns the absolute path to the best match, or None if the library is
    empty or no face could be detected in any library image.
    Falls back to the first library image on any error.
    """
    library_images = _get_library_images()
    if not library_images:
        return None

    try:
        library = _get_library_embeddings()
        if not library:
            return library_images[0]

        best_path, best_sim = library_images[0], -1.0
        for path, lib_emb in library:
            sim = cosine_similarity(face_embedding, lib_emb)
            if sim > best_sim:
                best_sim = sim
                best_path = path
        return best_path
    except Exception:
        return library_images[0]
