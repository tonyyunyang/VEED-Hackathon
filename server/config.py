import os

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

# Backward compatibility: keep the old dummy switch available, but default it
# from the selected tracker backend so the backend choice is explicit.
DUMMY_TRACKING = _env_bool("DUMMY_TRACKING", TRACKER_BACKEND == "dummy")
