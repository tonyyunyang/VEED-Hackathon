import os
import sys

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(__file__)
ROOT_DIR = os.path.dirname(BASE_DIR)

# Prefer the repo-root .env when present, while keeping missing files non-fatal.
load_dotenv(os.path.join(ROOT_DIR, ".env"))


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return int(value)


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return float(value)


def _env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None:
        return default
    stripped = value.strip()
    return stripped if stripped else default


def _env_path(name: str, default: str, *, base_dir: str = ROOT_DIR) -> str:
    value = os.getenv(name)
    candidate = default if value is None or value.strip() == "" else value.strip()
    if os.path.isabs(candidate):
        return candidate
    return os.path.abspath(os.path.join(base_dir, candidate))


STORAGE_DIR = os.path.abspath(os.getenv("STORAGE_DIR", os.path.join(BASE_DIR, "storage")))

TRACKER_BACKEND = (
    os.getenv("TRACKER_BACKEND", "movie_like_shots").strip().lower() or "movie_like_shots"
)
TRACKER_TYPE = os.getenv("TRACKER_TYPE", "ocsort").strip().lower() or "ocsort"
TRACKER_DEVICE = os.getenv("TRACKER_DEVICE", "auto").strip().lower() or "auto"
TRACKER_DET_SIZE = _env_int("TRACKER_DET_SIZE", 640)
TRACKER_DET_THRESH = _env_float("TRACKER_DET_THRESH", 0.35)
TRACKER_NMS_THRESH = _env_float("TRACKER_NMS_THRESH", 0.4)
TRACKER_NUM_BINS = _env_int("TRACKER_NUM_BINS", 64)
TRACKER_SHOT_CHANGE_THRESHOLD = _env_float("TRACKER_SHOT_CHANGE_THRESHOLD", 0.4)
TRACKER_SIMILARITY_THRESHOLD = _env_float("TRACKER_SIMILARITY_THRESHOLD", 0.4)
TRACKER_FILTER_TRACKS = _env_bool("TRACKER_FILTER_TRACKS", False)
TRACKER_MIN_TRACK_LENGTH = _env_int("TRACKER_MIN_TRACK_LENGTH", 10)
TRACKER_MIN_TRACK_MEDIAN_AREA = _env_float("TRACKER_MIN_TRACK_MEDIAN_AREA", 2500.0)
TRACKER_FILTER_CONFIDENCE = _env_bool("TRACKER_FILTER_CONFIDENCE", False)
TRACKER_MIN_CONFIDENCE = _env_float("TRACKER_MIN_CONFIDENCE", 0.5)
TRACKER_USE_SHOT_CHANGE = _env_bool("TRACKER_USE_SHOT_CHANGE", True)
TRACKER_USE_SHARED_MEMORY = _env_bool("TRACKER_USE_SHARED_MEMORY", True)
TRACKER_TIMEOUT_SECONDS = _env_int("TRACKER_TIMEOUT_SECONDS", 600)
TRACKER_FRAME_SUBSAMPLE = _env_int(
    "TRACKER_FRAME_SUBSAMPLE",
    _env_int("FRAME_SUBSAMPLE", 5),
)
FACE_ANALYSIS_DEVICE = os.getenv("FACE_ANALYSIS_DEVICE", TRACKER_DEVICE).strip().lower() or "auto"
FRAME_SUBSAMPLE = TRACKER_FRAME_SUBSAMPLE

ENABLE_LIPSYNC = _env_bool("ENABLE_LIPSYNC", False)
FAL_KEY = os.getenv("FAL_KEY", "")  # for lipsync
LIPSYNC_RESOLUTION = os.getenv("LIPSYNC_RESOLUTION", "480p")

FACE_SWAPPER_BACKEND = _env_str("FACE_SWAPPER_BACKEND", "insightface").lower()
ENABLE_FACE_METADATA_ENRICHMENT = _env_bool(
    "ENABLE_FACE_METADATA_ENRICHMENT",
    FACE_SWAPPER_BACKEND == "insightface",
)
FACE_SWAP_REFERENCE_IMAGE = os.getenv("FACE_SWAP_REFERENCE_IMAGE", "").strip()
FACE_SWAP_REFERENCE_FACES_DIR = _env_path(
    "FACE_SWAP_REFERENCE_FACES_DIR",
    os.path.join("server", "reference_faces"),
)
FACE_SWAP_ALLOW_TARGET_THUMBNAIL_FALLBACK = _env_bool(
    "FACE_SWAP_ALLOW_TARGET_THUMBNAIL_FALLBACK",
    True,
)

FACEFUSION_DIR = _env_path("FACEFUSION_DIR", "facefusion-VEED")
FACEFUSION_PYTHON = _env_str("FACEFUSION_PYTHON", sys.executable)
FACEFUSION_EXECUTION_PROVIDER = _env_str(
    "FACEFUSION_EXECUTION_PROVIDER",
    "coreml" if sys.platform == "darwin" else "cpu",
).lower()
FACEFUSION_BYPASS_CONTENT_ANALYSER = _env_bool(
    "FACEFUSION_BYPASS_CONTENT_ANALYSER",
    True,
)
FACEFUSION_SWAP_MODEL = _env_str("FACEFUSION_SWAP_MODEL", "hyperswap_1a_256")
FACEFUSION_PIXEL_BOOST = _env_str("FACEFUSION_PIXEL_BOOST", "512x512")
FACEFUSION_ENABLE_ENHANCER = _env_bool("FACEFUSION_ENABLE_ENHANCER", True)
FACEFUSION_OUTPUT_VIDEO_QUALITY = _env_int("FACEFUSION_OUTPUT_VIDEO_QUALITY", 90)
FACEFUSION_THREAD_COUNT = _env_int("FACEFUSION_THREAD_COUNT", 4)
FACEFUSION_KEEP_INTERMEDIATES = _env_bool("FACEFUSION_KEEP_INTERMEDIATES", False)

# Backward compatibility: keep the old dummy switch available, but default it
# from the selected tracker backend so the backend choice is explicit.
DUMMY_TRACKING = _env_bool("DUMMY_TRACKING", TRACKER_BACKEND == "dummy")
